import pytest
from benchmark_runner.stats import percentile, summarize


def test_percentile_interpolates_linearly():
    assert percentile([10, 20, 30, 40], 50) == 25
    assert percentile([10, 20, 30, 40], 100) == 40
    assert percentile([10, 20, 30, 40], 0) == 10


def test_percentile_single_value_and_unsorted_input():
    assert percentile([7], 99) == 7
    assert percentile([3, 1, 2], 50) == 2


def test_percentile_empty_is_none():
    assert percentile([], 95) is None


def test_summarize_counts_only_window_completions():
    s = summarize([100.0, 200.0, 300.0], window_s=300)
    assert s.throughput_qps == pytest.approx(0.01)
    assert s.p50_ms == 200.0


def test_summarize_without_samples_has_zero_qps_and_blank_latency():
    s = summarize([], window_s=300)
    assert s.throughput_qps == 0
    assert s.p50_ms is None and s.p95_ms is None and s.p99_ms is None


def test_prom_selector_targets_one_exact_container():
    from benchmark_runner.telemetry import prom_selector
    assert prom_selector("abc") == '{id="/system.slice/docker-abc.scope"}'


def test_throttling_cross_check_tolerates_sampling_skew_only():
    from benchmark_runner.telemetry import sources_agree
    assert sources_agree(42.8, 44.0)
    assert sources_agree(0.0, 0.0)
    assert sources_agree(1.0, 3.0)
    assert not sources_agree(0.0, 44.0)
    assert not sources_agree(100.0, 200.0)
    assert sources_agree(5.0, None)


def test_spill_detected_from_writes_when_a_crash_resets_pg_counters(monkeypatch):
    from benchmark_runner import engine_stats
    monkeypatch.setattr(engine_stats, "container_logs", lambda *a: "")
    before = {"temp_files": 5, "temp_bytes": 10}
    after = {"temp_files": 0, "temp_bytes": 0}
    assert engine_stats.spill_evidence("postgresql", before, after, 0, written_bytes=700 * 2**20)[0] is True
    assert engine_stats.spill_evidence("postgresql", before, after, 0, written_bytes=2**20)[0] is False


def test_mongo_background_writes_are_not_a_spill(monkeypatch):
    from benchmark_runner import engine_stats
    monkeypatch.setattr(engine_stats, "container_logs", lambda *a: "")
    counters = {"sort_spills": 0, "group_spills": 0}
    assert engine_stats.spill_evidence("mongodb", counters, counters, 0, written_bytes=2**30)[0] is False


def test_io_stat_sums_write_bytes_across_devices(tmp_path):
    from benchmark_runner.telemetry import write_bytes
    p = tmp_path / "io.stat"
    p.write_text("259:0 rbytes=10 wbytes=100 rios=1 wios=1\n8:0 rbytes=5 wbytes=23 rios=1 wios=1\n")
    assert write_bytes(p) == 123
    assert write_bytes(tmp_path / "missing") == 0


def test_oom_evidence_keeps_engine_and_kernel_lines(monkeypatch):
    from types import SimpleNamespace
    from benchmark_runner import engine_stats
    monkeypatch.setattr(engine_stats, "container_logs",
                        lambda *a: "LOG: normal\nLOG: client backend (PID 44) was terminated by signal 9: Killed\n")
    monkeypatch.setattr(engine_stats.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout="kernel: otra cosa\nkernel: Memory cgroup out of memory: Killed process 44 (postgres)\n"))
    text = engine_stats.oom_evidence("postgresql", 0, {"OOMKilled": False})
    assert "signal 9" in text and "Memory cgroup out of memory" in text and "OOMKilled=False" in text
    assert "normal" not in text and "otra cosa" not in text
