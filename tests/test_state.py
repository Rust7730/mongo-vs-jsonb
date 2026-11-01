from orchestrator.state import Journal, build_plan, derive, extend_plan


def test_plan_has_108_main_and_54_annex_runs():
    plan = build_plan(seed=7)
    assert len([r for r in plan if r["variant"] == "strict"]) == 108
    annex = [r for r in plan if r["variant"] == "annex"]
    assert len(annex) == 54
    assert {r["query"] for r in annex} == {"Q2"}
    assert {(r["profile"], r["concurrency"]) for r in annex} == {(p, c) for p in "ABC" for c in (1, 10, 50)}


def test_full_annex_keeps_the_official_order_of_the_previous_plan():
    strict = [r for r in build_plan(seed=7) if r["variant"] == "strict"]
    assert strict == [r for r in build_plan(seed=7, annex_cells=[("C", 50)]) if r["variant"] == "strict"]


def test_extend_plan_preserves_done_runs_and_appends_only_the_missing_ones():
    old = build_plan(seed=7, annex_cells=[("C", 50)])
    new = extend_plan(old, build_plan(seed=7))
    assert len(old) == 114 and len(new) == 162
    assert new[:114] == old
    assert len({r["id"] for r in new}) == 162
    assert all(r["variant"] == "annex" for r in new[114:])


def test_extending_a_finished_campaign_leaves_only_the_new_runs_pending():
    old = build_plan(seed=7, annex_cells=[("C", 50)])
    events = [{"event": "campaign_started"}, *({"event": "run_finished", "run": r["id"]} for r in old), {"event": "done"}]
    d = derive(extend_plan(old, build_plan(seed=7)), events)
    assert len(d.pending) == 48 and all(r["variant"] == "annex" for r in d.pending)


def test_plan_is_deterministic_and_seed_sensitive():
    assert build_plan(seed=7) == build_plan(seed=7)
    assert build_plan(seed=7) != build_plan(seed=8)


def test_plan_finishes_each_repetition_before_the_next():
    reps = [r["rep"] for r in build_plan(seed=1) if r["variant"] == "strict"]
    assert reps == sorted(reps)


def test_run_ids_are_unique():
    plan = build_plan(seed=1)
    assert len({r["id"] for r in plan}) == len(plan)


def test_journal_survives_a_truncated_last_line(tmp_path):
    p = tmp_path / "j.jsonl"
    j = Journal(p)
    j.append("run_started", run="a")
    with p.open("a") as f:
        f.write('{"event":"run_fin')
    assert [e["event"] for e in Journal(p).read()] == ["run_started"]


def ev(event, **kw):
    return {"event": event, **kw}


def test_derive_pending_skips_finished_and_repeats_unfinished():
    plan = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    d = derive(plan, [ev("run_started", run="a"), ev("run_finished", run="a"), ev("run_started", run="b")])
    assert [r["id"] for r in d.pending] == ["b", "c"]
    assert d.interrupted == "b"


def test_derive_suspect_goes_to_the_tail_once():
    plan = [{"id": "a"}, {"id": "b"}]
    d = derive(plan, [ev("run_started", run="a"), ev("run_suspect", run="a")])
    assert [r["id"] for r in d.pending] == ["b", "a"]
    assert d.suspects == {"a"}
    assert d.interrupted is None


def test_derive_state_transitions():
    plan = [{"id": "a"}]
    assert derive(plan, []).state == "new"
    assert derive(plan, [ev("campaign_started")]).state == "running"
    assert derive(plan, [ev("campaign_started"), ev("paused")]).state == "paused"
    assert derive(plan, [ev("campaign_started"), ev("paused"), ev("resumed")]).state == "running"
    assert derive(plan, [ev("campaign_started"), ev("halted", reason="x")]).state == "halted"
    assert derive(plan, [ev("campaign_started"), ev("done")]).state == "done"
