import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CSV_HEADER = [
    "timestamp_epoch", "engine", "profile", "query_id", "concurrency", "run_number",
    "throughput_qps", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms",
    "cpu_throttled_seconds", "max_rss_mb", "disk_spill", "status",
]

ENGINES = ("mongodb", "postgresql")
PROFILES = {"A": "PROFILE_A_BASELINE", "B": "PROFILE_B_MEDIUM", "C": "PROFILE_C_SEVERE"}
QUERIES = ("Q1", "Q2")
CONCURRENCIES = (1, 10, 50)
REPETITIONS = 3

# Solo Q2 cambia entre variantes; Q1 usa los valores por defecto de cada motor.
VARIANTS = {
    "strict": {"mongodb": {"allowDiskUse": False}, "postgresql": {"work_mem": "4MB"}},
    "annex": {"mongodb": {"allowDiskUse": True}, "postgresql": {"work_mem": "64MB"}},
}

DB_CPUS = {0, 1, 2, 3}
RUNNER_CPUS = {4, 5, 10, 11}
IDLE_SIBLING_CPUS = {6, 7, 8, 9}

MONGO_URI = "mongodb://127.0.0.1:27018/?directConnection=true"
MONGO_DB = "bench"
PG_DSN = "host=127.0.0.1 port=5433 user=bench dbname=bench"
PROMETHEUS_URL = "http://127.0.0.1:9091"

CONTAINERS = {"mongodb": "bench-mongodb", "postgresql": "bench-postgresql"}

SCALE = float(os.environ.get("BENCH_PHASE_SCALE", "1"))
WARMUP_S = 60 * SCALE
MEASURE_S = 300 * SCALE
COOLDOWN_S = 60 * SCALE

# Si un worker queda colgado tras cerrar la ventana, se termina el proceso.
WORKER_JOIN_GRACE_S = 25
# Fracción mínima de muestras de 1 s esperadas para aceptar la telemetría.
MIN_SAMPLE_RATIO = 0.8
# Ocupación media de los hermanos SMT libres que marca una corrida como ruidosa.
NOISE_BUSY_PCT = 30.0

STATE_DIR = ROOT / os.environ.get("BENCH_STATE_DIR", "state")
RESULTS_DIR = ROOT / os.environ.get("BENCH_RESULTS_DIR", "results")
DATA_PATH = ROOT / os.environ.get("BENCH_DATA", "data/orders.ndjson")
REHEARSAL = os.environ.get("BENCH_REHEARSAL") == "1"
