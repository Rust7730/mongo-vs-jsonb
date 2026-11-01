"""Comprobaciones antes de arrancar o reanudar. No abren incidencias: informan al usuario."""
import subprocess
from pathlib import Path

from benchmark_runner.config import DATA_PATH, REHEARSAL, STATE_DIR
from benchmark_runner.telemetry import host_busy_pct

from . import host, manifest

MIN_DISK_GIB = 10
MIN_MEM_GIB = 6
MAX_BUSY_PCT = 25


def _ok(cmd):
    return subprocess.run(cmd, capture_output=True).returncode == 0


def checks():
    disk, mem = host.disk_free_gib(), host.mem_available_gib()
    result = [
        ("Docker activo", _ok(["docker", "info"]), ""),
        ("docker compose", _ok(["docker", "compose", "version"]), "instala con: sudo pacman -S docker-compose"),
        ("cgroups v2", Path("/sys/fs/cgroup/cgroup.controllers").exists(), ""),
        ("Dataset cargado", (STATE_DIR / "dataset.json").exists(), "ejecuta load-data"),
        (f"Disco libre ≥ {MIN_DISK_GIB} GiB", disk >= MIN_DISK_GIB, f"{disk:.0f} GiB"),
    ]
    if (STATE_DIR / "manifest.json").exists():
        drift = manifest.changed(STATE_DIR / "manifest.json", DATA_PATH)
        result.append(("Manifiesto intacto", not drift, ", ".join(drift)))
    if not REHEARSAL:
        busy = host_busy_pct(set(range(12)))
        result += [
            (f"RAM disponible ≥ {MIN_MEM_GIB} GiB", mem >= MIN_MEM_GIB, f"{mem:.1f} GiB; cierra navegadores"),
            (f"Host en reposo (< {MAX_BUSY_PCT} % CPU)", busy < MAX_BUSY_PCT, f"{busy:.0f} % ocupado"),
        ]
    return result
