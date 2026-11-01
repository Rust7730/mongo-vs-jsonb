"""Lecturas de Prometheus y de los archivos del cgroup del contenedor."""
import csv
import json
import os
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .config import IDLE_SIBLING_CPUS, PROMETHEUS_URL

METRIC_SOURCE = os.environ.get("BENCH_METRIC_SOURCE", "prometheus")


def prom_query(expr, at):
    params = urllib.parse.urlencode({"query": expr, "time": at})
    with urllib.request.urlopen(f"{PROMETHEUS_URL}/api/v1/query?{params}", timeout=10) as r:
        result = json.load(r)["data"]["result"]
    return float(result[0]["value"][1]) if result else None


def prom_selector(cid):
    # Cada corrida crea un contenedor con el mismo nombre y cAdvisor publica marcas de tiempo
    # propias, así que la serie del contenedor anterior sigue visible 5 min: se filtra por ID.
    return f'{{id="/system.slice/docker-{cid}.scope"}}'


def prom_metrics(cid, t0, t1):
    """Devuelve (throttled_s, max_rss_bytes, samples) de la ventana de medición."""
    window = max(1, round(t1 - t0))
    sel = prom_selector(cid)
    start = prom_query(f"container_cpu_cfs_throttled_seconds_total{sel}", t0) or 0.0
    end = prom_query(f"container_cpu_cfs_throttled_seconds_total{sel}", t1)
    rss = prom_query(f"max_over_time(container_memory_rss{sel}[{window}s])", t1)
    samples = prom_query(f"count_over_time(container_memory_rss{sel}[{window}s])", t1)
    throttled = None if end is None else max(0.0, end - start)
    return throttled, rss, samples or 0


def sources_agree(prometheus_s, cgroup_s):
    """Prometheus y el cgroup miden lo mismo; solo se tolera el desfase de muestreo."""
    if prometheus_s is None or cgroup_s is None:
        return True
    return abs(prometheus_s - cgroup_s) <= max(5.0, 0.15 * max(prometheus_s, cgroup_s))


def container_id(name):
    out = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", name], capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def container_state(name):
    out = subprocess.run(["docker", "inspect", "-f", "{{json .State}}", name], capture_output=True, text=True)
    return json.loads(out.stdout) if out.returncode == 0 else {}


def container_logs(name, since_epoch):
    out = subprocess.run(["docker", "logs", "--since", str(int(since_epoch)), name],
                         capture_output=True, text=True, errors="replace")
    return out.stdout + out.stderr


def _kv_file(path):
    return {k: int(v) for k, v in (line.split() for line in path.read_text().splitlines())}


def write_bytes(path):
    if not path.exists():
        return 0
    fields = (f.partition("=") for line in path.read_text().splitlines() for f in line.split()[1:])
    return sum(int(value) for key, _, value in fields if key == "wbytes")


class Cgroup:
    def __init__(self, cid):
        self.path = Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope")

    def exists(self):
        return self.path.exists()

    def snapshot(self):
        mem = _kv_file(self.path / "memory.stat")
        cpu = _kv_file(self.path / "cpu.stat")
        return {
            "anon": mem["anon"], "shmem": mem["shmem"], "file": mem["file"],
            "usage_usec": cpu["usage_usec"], "throttled_usec": cpu.get("throttled_usec", 0),
            "nr_throttled": cpu.get("nr_throttled", 0),
            "current": int((self.path / "memory.current").read_text()),
            "peak": int((self.path / "memory.peak").read_text()),
            "oom_kill": _kv_file(self.path / "memory.events")["oom_kill"],
            "wbytes": write_bytes(self.path / "io.stat"),
        }


def _cpu_times(cpus):
    busy = total = 0
    for line in Path("/proc/stat").read_text().splitlines():
        head, *fields = line.split()
        if head.startswith("cpu") and head != "cpu" and int(head[3:]) in cpus:
            values = [int(v) for v in fields[:8]]
            total += sum(values)
            busy += sum(values) - values[3] - values[4]
    return busy, total


def host_busy_pct(cpus, seconds=2):
    b0, t0 = _cpu_times(cpus)
    time.sleep(seconds)
    b1, t1 = _cpu_times(cpus)
    return 100 * (b1 - b0) / max(1, t1 - t0)


class Sampler(threading.Thread):
    """Serie de 1 s independiente de Prometheus; conserva el último valor si el cgroup desaparece."""

    FIELDS = ["t", "anon", "shmem", "file", "current", "usage_usec", "throttled_usec", "nr_throttled", "peak",
              "wbytes"]

    def __init__(self, cgroup, out_path):
        super().__init__(daemon=True)
        self.cgroup, self.out_path = cgroup, out_path
        self.halt = threading.Event()
        self.first = self.last = {}
        self.window_start = self.window_end = None
        self.mark_start = self.mark_end = False
        self.b0, self.t0 = self.b1, self.t1 = (0, 0)

    def mark(self, which):
        setattr(self, f"mark_{which}", True)

    def run(self):
        with open(self.out_path, "w", newline="") as f:
            out = csv.DictWriter(f, fieldnames=self.FIELDS, extrasaction="ignore")
            out.writeheader()
            while not self.halt.wait(1):
                try:
                    snap = self.cgroup.snapshot()
                except (OSError, KeyError, ValueError):
                    continue
                self.first = self.first or snap
                self.last = snap
                if self.mark_start and not self.window_start:
                    self.window_start = snap
                    self.b0, self.t0 = _cpu_times(IDLE_SIBLING_CPUS)
                if self.mark_end and not self.window_end:
                    self.window_end = snap
                    self.b1, self.t1 = _cpu_times(IDLE_SIBLING_CPUS)
                out.writerow({"t": time.time(), **snap})
                f.flush()

    def stop(self):
        self.halt.set()
        self.join(5)

    def written_bytes(self):
        return self.last.get("wbytes", 0) - self.first.get("wbytes", 0)

    def idle_sibling_busy_pct(self):
        return 100 * (self.b1 - self.b0) / max(1, self.t1 - self.t0)

    def cpu_seconds(self):
        if not (self.window_start and self.window_end):
            return None
        return (self.window_end["usage_usec"] - self.window_start["usage_usec"]) / 1e6

    def throttled_seconds(self):
        if not (self.window_start and self.window_end):
            return None
        return (self.window_end["throttled_usec"] - self.window_start["throttled_usec"]) / 1e6
