"""Separa los resultados del experimento de las fallas de infraestructura.

Un OOM, un spill o un error de memoria del motor son datos: van al CSV y no
disparan nada. Solo una falla ajena al experimento abre una incidencia.
"""
from dataclasses import dataclass

MONGO_KINDS = {146: "memory", 292: "memory", 16819: "memory", 16945: "memory", 50: "cancelled"}
PG_KINDS = {"53200": "memory", "57014": "cancelled", "57P01": "conn_lost", "57P02": "conn_lost",
            "57P03": "conn_lost"}


@dataclass(frozen=True)
class Signals:
    completed: int
    censored: int
    memory_errors: int
    conn_lost: int
    other_errors: int
    oom_kills: int
    spill: bool
    telemetry_ok: bool


@dataclass(frozen=True)
class Verdict:
    fault: bool
    status: str | None
    reason: str


def error_kind(engine, code):
    table = MONGO_KINDS if engine == "mongodb" else PG_KINDS
    return table.get(code, "other")


def verdict(s):
    if s.oom_kills > 0:
        return Verdict(False, "oom", "oom_kill")
    if not s.telemetry_ok:
        return Verdict(True, None, "telemetry_gap")
    if s.conn_lost > 0:
        return Verdict(True, None, "connection_lost")
    if s.other_errors > 0:
        return Verdict(True, None, "unexpected_engine_error")
    if s.memory_errors > 0:
        return Verdict(False, "error", "engine_memory")
    if s.completed == 0:
        if s.censored > 0:
            return Verdict(False, "error", "no_completions")
        return Verdict(True, None, "no_activity")
    if s.spill:
        return Verdict(False, "spill", "disk_spill")
    return Verdict(False, "ok", "ok")
