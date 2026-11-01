"""Operaciones sobre Docker y el host. Todo error aquí es una falla de infraestructura."""
import json
import shutil
import subprocess
import time
from pathlib import Path

import psycopg
import pymongo

from benchmark_runner.config import CONTAINERS, MONGO_URI, PG_DSN, ROOT, STATE_DIR

ALPINE = "alpine:3.22@sha256:2e0b81d60597f449baa56dc25d355367869d2dca4cd57e866f1e2b52af3eb55f"
TELEMETRY = ("cadvisor", "node-exporter", "prometheus")
ENGINE_READY_TIMEOUT_S = 240
CPU_SYSFS = "/sys/devices/system/cpu/cpu*/cpufreq"


class Fault(Exception):
    def __init__(self, reason, detail=""):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail = reason, str(detail)[-4000:]


def _sh(cmd, reason, timeout=180):
    try:
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise Fault(reason, exc) from exc
    if out.returncode != 0:
        raise Fault(reason, out.stdout + out.stderr)
    return out.stdout


def compose(*args, profile="A", reason="compose_failed"):
    return _sh(["docker", "compose", "--env-file", f"profiles/{profile}.env", *args], reason)


def start_telemetry():
    compose("up", "-d", *TELEMETRY, reason="telemetry_start_failed")


def stop_telemetry():
    compose("stop", *TELEMETRY)


def recreate_telemetry():
    compose("up", "-d", "--force-recreate", *TELEMETRY, reason="telemetry_start_failed")


def stop_engines():
    compose("stop", "-t", "60", *CONTAINERS)
    compose("rm", "-f", *CONTAINERS)


def start_engine(engine, profile):
    compose("up", "-d", "--force-recreate", "--no-deps", engine, profile=profile, reason="engine_start_failed")


def wait_ready(engine, timeout=ENGINE_READY_TIMEOUT_S):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            if engine == "mongodb":
                with pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000) as client:
                    client.admin.command("ping")
            else:
                with psycopg.connect(PG_DSN, connect_timeout=2, autocommit=True) as conn:
                    conn.execute("SELECT 1")
            return
        except Exception as exc:
            last = exc
            time.sleep(1)
    raise Fault("engine_not_ready", f"{engine}: {last}")


def privileged(script, reason):
    _sh(["docker", "run", "--rm", "--privileged", "--cpuset-cpus", "4,5,10,11", ALPINE, "sh", "-c", script],
        reason, timeout=120)


def drop_caches():
    privileged("sync; echo 3 > /proc/sys/vm/drop_caches", "drop_caches_failed")


def _energy_file():
    return STATE_DIR / "energy.json"


def energy_performance():
    """Fija CPU en rendimiento; guarda lo previo la primera vez para poder restaurarlo."""
    cpu0 = Path("/sys/devices/system/cpu/cpu0/cpufreq")
    if not _energy_file().exists():
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _energy_file().write_text(json.dumps({
            "governor": (cpu0 / "scaling_governor").read_text().strip(),
            "epp": (cpu0 / "energy_performance_preference").read_text().strip(),
        }))
    privileged(f"for f in {CPU_SYSFS}/scaling_governor; do echo performance > $f; done", "energy_failed")


def energy_restore():
    if not _energy_file().exists():
        return
    saved = json.loads(_energy_file().read_text())
    privileged(f"for f in {CPU_SYSFS}/scaling_governor; do echo {saved['governor']} > $f; done; "
               f"for f in {CPU_SYSFS}/energy_performance_preference; do echo {saved['epp']} > $f; done",
               "energy_failed")
    _energy_file().unlink()


def disk_free_gib():
    return shutil.disk_usage("/var/lib/docker" if Path("/var/lib/docker").exists() else ROOT).free / 2**30


def mem_available_gib():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 2**20
    return 0.0
