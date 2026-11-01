"""Contadores internos y señales de spill de cada motor, sin distorsionar la medición."""
import subprocess

import psycopg
import pymongo

from .config import CONTAINERS, MONGO_DB, MONGO_URI, PG_DSN
from .telemetry import container_logs

# La carga es de solo lectura: en PostgreSQL, escribir esto a disco implica archivos temporales.
# Hace falta porque un OOM reinicia pg_stat_database y mata las consultas antes de registrarlos.
PG_SPILL_WRITE_BYTES = 32 * 2**20


def counters(engine):
    if engine == "mongodb":
        with pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000) as client:
            query = client.admin.command("serverStatus")["metrics"]["query"]
        return {"sort_spills": int(query.get("sort", {}).get("spillToDisk", 0)),
                "group_spills": int(query.get("group", {}).get("spills", 0))}
    with psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn:
        files, size = conn.execute(
            "SELECT temp_files, temp_bytes FROM pg_stat_database WHERE datname = current_database()").fetchone()
    return {"temp_files": int(files), "temp_bytes": int(size)}


def row_count(engine):
    if engine == "mongodb":
        with pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000) as client:
            return client[MONGO_DB]["orders"].estimated_document_count()
    with psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn:
        return int(conn.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'orders'").fetchone()[0])


def spill_evidence(engine, before, after, since_epoch, written_bytes=0):
    """Devuelve (spill, líneas de log que lo respaldan)."""
    marker = '"usedDisk":true' if engine == "mongodb" else "temporary file:"
    lines = [l for l in container_logs(CONTAINERS[engine], since_epoch).splitlines() if marker in l]
    grew = bool(after) and any(after[k] > before.get(k, 0) for k in after if k != "temp_bytes")
    wrote = engine == "postgresql" and written_bytes >= PG_SPILL_WRITE_BYTES
    if wrote:
        lines.append(f"cgroup io.stat: {written_bytes} bytes escritos con carga de solo lectura")
    return grew or wrote or bool(lines), lines


def oom_evidence(engine, since_epoch, state):
    """Reúne la evidencia antes de que la corrida siguiente elimine el contenedor."""
    engine_lines = [l for l in container_logs(CONTAINERS[engine], since_epoch).splitlines()
                    if "signal 9" in l or "out of memory" in l.lower()]
    journal = subprocess.run(["journalctl", "-k", "--since", f"@{int(since_epoch)}", "--no-pager"],
                             capture_output=True, text=True).stdout
    kernel_lines = [l for l in journal.splitlines() if "Memory cgroup out of memory" in l]
    head = [f"docker inspect OOMKilled={state.get('OOMKilled')}",
            f"kernel: {len(kernel_lines)} eventos de OOM en el cgroup; motor: {len(engine_lines)} líneas"]
    return "\n".join(head + kernel_lines[:20] + engine_lines[:20]) + "\n"
