"""Sonda complementaria de M2: explica los buffers observados. No forma parte del CSV.

- MongoDB: cuánto se relee del disco en una segunda ejecución de Q2, por tamaño de caché.
- PostgreSQL: qué plan elige Q1 según work_mem.
"""
import json
import re
import time

import psycopg
import pymongo

from benchmark_runner.config import MONGO_DB, MONGO_URI, PG_DSN, RESULTS_DIR
from benchmark_runner.workers import load_query
from orchestrator import host


def cache_stats(client):
    cache = client.admin.command("serverStatus")["wiredTiger"]["cache"]
    return {"leido_mb": cache["bytes read into cache"] / 2**20, "maximo_mb": cache["maximum bytes configured"] / 2**20}


def timed_q2(client):
    start = time.monotonic()
    list(client[MONGO_DB].orders.aggregate(load_query("mongodb", "Q2"), allowDiskUse=False))
    return time.monotonic() - start


def mongo_case(profile):
    host.stop_engines()
    host.drop_caches()
    host.start_engine("mongodb", profile)
    host.wait_ready("mongodb")
    with pymongo.MongoClient(MONGO_URI) as client:
        timed_q2(client)
        before = cache_stats(client)
        seconds = timed_q2(client)
        after = cache_stats(client)
        stats = client[MONGO_DB].command("collStats", "orders")
    return {"cache_wt_mb": after["maximo_mb"], "coleccion_comprimida_mb": round(stats["storageSize"] / 2**20),
            "coleccion_sin_comprimir_mb": round(stats["size"] / 2**20),
            "releido_en_2a_ejecucion_mb": round(after["leido_mb"] - before["leido_mb"], 1),
            "segundos_2a_ejecucion": round(seconds, 2)}


def pg_case(work_mem):
    with psycopg.connect(PG_DSN, autocommit=True) as conn:
        conn.execute(f"SET work_mem = '{work_mem}'")
        text = "\n".join(r[0] for r in conn.execute("EXPLAIN (ANALYZE, BUFFERS) " + load_query("postgresql", "Q1")))
    return {"nodo_raiz": text.splitlines()[0].split("  ")[0],
            "disco_kb": sum(map(int, re.findall(r"external merge\s+Disk: (\d+)kB", text))),
            "sort_metodos": sorted(set(re.findall(r"Sort Method: ([a-zN\- ]+?)(?:  |$)", text, re.M))),
            "milisegundos": float(re.findall(r"Execution Time: ([\d.]+)", text)[0])}


def main():
    result = {"mongodb_q2": {p: mongo_case(p) for p in "ABC"}}
    host.stop_engines()
    host.drop_caches()
    host.start_engine("postgresql", "C")
    host.wait_ready("postgresql")
    result["postgresql_q1"] = {m: pg_case(m) for m in ("4MB", "64MB", "256MB")}
    host.stop_engines()
    out = RESULTS_DIR / "sonda_buffers.json"
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
