"""Ejecuta una corrida sobre un motor ya levantado y devuelve su fila del CSV."""
import json
import time
from dataclasses import asdict, dataclass

from . import engine_stats
from .classify import Signals, verdict
from .config import (CONTAINERS, COOLDOWN_S, MEASURE_S, MIN_SAMPLE_RATIO, NOISE_BUSY_PCT, PROFILES,
                     WARMUP_S, WORKER_JOIN_GRACE_S)
from .stats import summarize
from .telemetry import (METRIC_SOURCE, Cgroup, Sampler, container_id, container_state, prom_metrics,
                        sources_agree)
from .workers import CTX, worker


class Aborted(Exception):
    pass


@dataclass
class Outcome:
    row: dict
    fault: bool
    reason: str
    noisy: bool


def _wait(until, should_abort):
    while (remaining := until - time.monotonic()) > 0:
        if should_abort():
            raise Aborted()
        time.sleep(min(0.5, remaining))


def _read_samples(raw_dir):
    samples = []
    with (raw_dir / "latencies.jsonl").open("w") as merged:
        for path in sorted(raw_dir.glob("client-*.jsonl")):
            for line in path.read_text().splitlines():
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                merged.write(line + "\n")
            path.unlink()
    return samples


def _count(samples, kind):
    return sum(1 for s in samples if s["k"] == kind)


def execute(run, raw_dir, should_abort):
    raw_dir.mkdir(parents=True, exist_ok=True)
    engine, name = run["engine"], CONTAINERS[run["engine"]]
    cid = container_id(name)
    cgroup = Cgroup(cid)
    start_epoch = time.time()
    before = engine_stats.counters(engine)
    sampler = Sampler(cgroup, raw_dir / "series.csv")

    n = run["concurrency"]
    barrier = CTX.Barrier(n + 1)
    t_measure, t_end = CTX.Value("d", 0.0), CTX.Value("d", 0.0)
    clients = [CTX.Process(target=worker, daemon=True,
                           args=(run, raw_dir / f"client-{i:02d}.jsonl", barrier, t_measure, t_end))
               for i in range(n)]
    for c in clients:
        c.start()
    barrier.wait(timeout=60)
    t0 = time.monotonic() + WARMUP_S
    t_measure.value, t_end.value = t0, t0 + MEASURE_S
    sampler.start()
    barrier.wait(timeout=60)

    try:
        _wait(t0, should_abort)
        epoch0 = time.time()
        sampler.mark("start")
        _wait(t0 + MEASURE_S, should_abort)
        epoch1 = time.time()
        sampler.mark("end")
        deadline = time.monotonic() + WORKER_JOIN_GRACE_S
        hung = 0
        for c in clients:
            c.join(max(0, deadline - time.monotonic()))
            if c.is_alive():
                hung += 1
                c.terminate()
        _wait(t0 + MEASURE_S + COOLDOWN_S, should_abort)
    except Aborted:
        for c in clients:
            c.terminate()
        sampler.stop()
        raise
    sampler.stop()

    samples = _read_samples(raw_dir)
    in_window = [s for s in samples if 0 <= s["e"] <= MEASURE_S]
    latencies = [(s["e"] - s["s"]) * 1000 for s in in_window if s["k"] == "ok"]
    summary = summarize(latencies, MEASURE_S)

    state = container_state(name)
    running = state.get("Running", False)
    last = sampler.last
    oom_kills = int(last.get("oom_kill", 0)) + (1 if state.get("OOMKilled") and not last.get("oom_kill") else 0)
    after = engine_stats.counters(engine) if running else {}
    spill, spill_lines = engine_stats.spill_evidence(engine, before, after, start_epoch, sampler.written_bytes())

    if METRIC_SOURCE == "prometheus":
        try:
            throttled, rss_bytes, n_samples = prom_metrics(cid, epoch0, epoch1)
        except OSError:
            throttled, rss_bytes, n_samples = None, None, 0
    else:
        throttled = sampler.throttled_seconds()
        rss_bytes = last.get("anon")
        n_samples = MEASURE_S
    telemetry_ok = (throttled is not None and n_samples >= MEASURE_S * MIN_SAMPLE_RATIO
                    and sources_agree(throttled, sampler.throttled_seconds()))

    signals = Signals(
        completed=summary.completed, censored=_count(samples, "cancelled") + hung,
        memory_errors=_count(samples, "memory"), conn_lost=_count(samples, "conn_lost"),
        other_errors=_count(samples, "other"), oom_kills=oom_kills, spill=spill,
        telemetry_ok=telemetry_ok,
    )
    result = verdict(signals)
    noisy = sampler.idle_sibling_busy_pct() > NOISE_BUSY_PCT

    (raw_dir / "meta.json").write_text(json.dumps({
        "run": run, "signals": asdict(signals), "verdict": asdict(result), "noisy": noisy,
        "idle_sibling_busy_pct": sampler.idle_sibling_busy_pct(),
        "cpu_seconds": sampler.cpu_seconds(), "cgroup_throttled_seconds": sampler.throttled_seconds(),
        "nr_throttled_final": last.get("nr_throttled"), "memory_peak_bytes": last.get("peak"),
        "anon_final": last.get("anon"), "shmem_final": last.get("shmem"), "file_final": last.get("file"),
        "before": before, "after": after, "written_bytes": sampler.written_bytes(), "hung_clients": hung, "prometheus_samples": n_samples,
        "metric_source": METRIC_SOURCE,
    }, indent=1))
    if oom_kills:
        (raw_dir / "oom_evidence.log").write_text(engine_stats.oom_evidence(engine, start_epoch, state))
    if spill_lines:
        (raw_dir / "spill_evidence.log").write_text("\n".join(spill_lines) + "\n")

    row = {
        "timestamp_epoch": int(epoch0), "engine": engine, "profile": PROFILES[run["profile"]],
        "query_id": run["query"], "concurrency": n, "run_number": run["rep"],
        "throughput_qps": summary.throughput_qps, "latency_p50_ms": summary.p50_ms,
        "latency_p95_ms": summary.p95_ms, "latency_p99_ms": summary.p99_ms,
        "cpu_throttled_seconds": throttled,
        "max_rss_mb": None if rss_bytes is None else rss_bytes / 1048576,
        "disk_spill": spill, "status": result.status,
    }
    return Outcome(row, result.fault, result.reason, noisy)
