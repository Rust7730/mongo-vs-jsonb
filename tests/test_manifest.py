from orchestrator.manifest import fingerprint, prefix_intact


def test_csv_may_only_grow_at_the_end(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("a,b\n1,2\n")
    before = fingerprint(p)
    with p.open("a") as f:
        f.write("3,4\n")
    assert prefix_intact(p, before)
    p.write_text("a,b\n9,2\n3,4\n")
    assert not prefix_intact(p, before)


def test_truncated_csv_is_detected(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("a,b\n1,2\n")
    before = fingerprint(p)
    p.write_text("a,b\n")
    assert not prefix_intact(p, before)
