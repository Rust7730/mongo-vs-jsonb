"""Huella de todo lo que define el experimento: el subagente no puede alterarlo."""
import hashlib
import json

from benchmark_runner.config import ROOT

PROTECTED = ["docker-compose.yml", "telemetry/prometheus.yml", "profiles/*.env", "queries/*",
             "benchmark_runner/config.py", "benchmark_runner/workers.py",
             "benchmark_runner/classify.py", "benchmark_runner/stats.py"]


def _sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def compute(data_path=None):
    files = sorted(p for pattern in PROTECTED for p in ROOT.glob(pattern) if p.is_file())
    if data_path is not None and data_path.exists():
        files.append(data_path)
    return {str(p.relative_to(ROOT)): _sha256(p) for p in files}


def save(path, data_path=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(compute(data_path), indent=1, sort_keys=True))


def changed(path, data_path=None):
    expected = json.loads(path.read_text())
    current = compute(data_path)
    return sorted(k for k in expected.keys() | current.keys() if expected.get(k) != current.get(k))


def fingerprint(path):
    if not path.exists():
        return {"size": 0, "sha256": None}
    return {"size": path.stat().st_size, "sha256": _sha256(path)}


def prefix_intact(path, print_before):
    """Las filas previas deben seguir idénticas; solo se admite crecer por el final."""
    if print_before["size"] == 0:
        return True
    if not path.exists() or path.stat().st_size < print_before["size"]:
        return False
    with path.open("rb") as f:
        return hashlib.sha256(f.read(print_before["size"])).hexdigest() == print_before["sha256"]
