from benchmark_runner.config import CSV_HEADER
from benchmark_runner.csvout import append_row, existing_keys, row_key


def row(**kw):
    base = dict(timestamp_epoch=1, engine="mongodb", profile="PROFILE_A_BASELINE", query_id="Q1",
                concurrency=10, run_number=2, throughput_qps=1.5, latency_p50_ms=1, latency_p95_ms=2,
                latency_p99_ms=3, cpu_throttled_seconds=0, max_rss_mb=10, disk_spill=False, status="ok")
    return {**base, **kw}


def test_header_matches_the_playbook_exactly():
    assert ",".join(CSV_HEADER) == (
        "timestamp_epoch,engine,profile,query_id,concurrency,run_number,throughput_qps,"
        "latency_p50_ms,latency_p95_ms,latency_p99_ms,cpu_throttled_seconds,max_rss_mb,"
        "disk_spill,status")


def test_first_append_writes_header_and_booleans_lowercase(tmp_path):
    p = tmp_path / "m.csv"
    append_row(p, row())
    lines = p.read_text().splitlines()
    assert lines[0].startswith("timestamp_epoch,")
    assert lines[1].endswith(",false,ok")


def test_append_is_idempotent_per_run_key(tmp_path):
    p = tmp_path / "m.csv"
    append_row(p, row())
    append_row(p, row(status="spill"))
    assert len(p.read_text().splitlines()) == 2


def test_existing_keys(tmp_path):
    p = tmp_path / "m.csv"
    append_row(p, row())
    assert existing_keys(p) == {row_key(row())}
    assert existing_keys(tmp_path / "missing.csv") == set()


def test_none_latency_is_blank(tmp_path):
    p = tmp_path / "m.csv"
    append_row(p, row(latency_p50_ms=None, latency_p95_ms=None, latency_p99_ms=None))
    assert ",,," in p.read_text()
