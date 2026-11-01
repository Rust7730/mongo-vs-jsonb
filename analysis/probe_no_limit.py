"""Sonda complementaria de M2: Q2 sin Top-K, una ejecución por variante en perfil C.

No forma parte del CSV ni de la matriz. Existe porque ORDER BY ... LIMIT y $sort + $limit
mantienen solo 1000 filas en memoria, así que Q2 tal cual no presiona los buffers.
"""
import json
import re
import time

import psycopg
import pymongo
from pymongo.errors import OperationFailure

from benchmark_runner.config import MONGO_DB, MONGO_URI, PG_DSN, RESULTS_DIR
from benchmark_runner.workers import load_query
from orchestrator import host

OUT = RESULTS_DIR / "sonda_sin_limit"


def mongo(allow_disk_use):
    pipeline = [s for s in load_query("mongodb", "Q2") if "$limit" not in s]
    start = time.monotonic()
    with pymongo.MongoClient(MONGO_URI) as client:
        try:
            plan = client[MONGO_DB].command(
                "explain", {"aggregate": "orders", "pipeline": pipeline, "cursor": {}, "allowDiskUse": allow_disk_use},
                verbosity="executionStats")
        except OperationFailure as exc:
            return {"resultado": "error", "codigo": exc.code, "mensaje": str(exc)[:200]}, str(exc)
    text = json.dumps(plan, indent=1, default=str)
    return {"resultado": "ok", "segundos": round(time.monotonic() - start, 1),
            "usedDisk": '"usedDisk": true' in text,
            "spills": [int(n) for n in re.findall(r'"spills": (\d+)', text)]}, text


def postgres(work_mem):
    sql = load_query("postgresql", "Q2").replace("LIMIT 1000", "").strip()
    with psycopg.connect(PG_DSN, autocommit=True) as conn:
        conn.execute(f"SET work_mem = '{work_mem}'")
        text = "\n".join(r[0] for r in conn.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql))
    sort = next((l.strip() for l in text.splitlines() if "Sort Method" in l), "")
    return {"resultado": "ok", "sort": sort}, text


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for engine, cases in (("mongodb", (False, True)), ("postgresql", ("4MB", "64MB"))):
        host.stop_engines()
        host.drop_caches()
        host.start_engine(engine, "C")
        host.wait_ready(engine)
        for case in cases:
            label = f"{engine}-{case}"
            result, text = mongo(case) if engine == "mongodb" else postgres(case)
            (OUT / f"{label}.txt").write_text(text)
            summary[label] = result
    host.stop_engines()
    (OUT / "resumen.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
