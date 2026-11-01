from benchmark_runner.classify import Signals, error_kind, verdict


def sig(**kw):
    base = dict(completed=10, censored=0, memory_errors=0, conn_lost=0, other_errors=0,
                oom_kills=0, spill=False, telemetry_ok=True)
    return Signals(**{**base, **kw})


def test_mongo_memory_limit_codes_are_results():
    assert error_kind("mongodb", 292) == "memory"
    assert error_kind("mongodb", 16819) == "memory"
    assert error_kind("mongodb", 146) == "memory"


def test_mongo_maxtime_is_a_window_cancel():
    assert error_kind("mongodb", 50) == "cancelled"


def test_pg_codes():
    assert error_kind("postgresql", "53200") == "memory"
    assert error_kind("postgresql", "57014") == "cancelled"
    assert error_kind("postgresql", "57P01") == "conn_lost"
    assert error_kind("postgresql", "42P01") == "other"


def test_clean_run_is_ok():
    v = verdict(sig())
    assert (v.fault, v.status) == (False, "ok")


def test_spill_status():
    assert verdict(sig(spill=True)).status == "spill"


def test_oom_wins_over_everything_and_is_not_a_fault():
    v = verdict(sig(oom_kills=1, conn_lost=9, spill=True, memory_errors=2))
    assert (v.fault, v.status) == (False, "oom")


def test_engine_memory_error_is_a_result_not_a_fault():
    v = verdict(sig(memory_errors=3))
    assert (v.fault, v.status, v.reason) == (False, "error", "engine_memory")


def test_memory_error_outranks_spill():
    assert verdict(sig(memory_errors=1, spill=True)).status == "error"


def test_no_completions_under_contention_is_a_result():
    v = verdict(sig(completed=0, censored=50))
    assert (v.fault, v.status, v.reason) == (False, "error", "no_completions")


def test_connection_lost_without_oom_is_a_fault():
    assert verdict(sig(conn_lost=2)).fault is True


def test_unknown_engine_error_is_a_fault():
    assert verdict(sig(other_errors=1)).fault is True


def test_nothing_happened_is_a_fault():
    assert verdict(sig(completed=0, censored=0)).fault is True


def test_missing_telemetry_is_a_fault():
    assert verdict(sig(telemetry_ok=False)).fault is True
