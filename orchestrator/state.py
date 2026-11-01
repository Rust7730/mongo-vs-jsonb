import json
import os
import random
import time
from dataclasses import dataclass, field

from benchmark_runner.config import CONCURRENCIES, ENGINES, PROFILES, QUERIES, REPETITIONS


def _run(engine, profile, query, concurrency, rep, variant):
    suffix = "-annex" if variant == "annex" else ""
    return {
        "id": f"{engine}-{profile}-{query}-c{concurrency}-r{rep}{suffix}",
        "engine": engine, "profile": profile, "query": query,
        "concurrency": concurrency, "rep": rep, "variant": variant,
    }


def build_plan(seed, repetitions=REPETITIONS, annex_cells=None):
    rng = random.Random(seed)
    cells = annex_cells or [(p, c) for p in PROFILES for c in CONCURRENCIES]
    plan = []
    for rep in range(1, repetitions + 1):
        block = [_run(e, p, q, c, rep, "strict")
                 for e in ENGINES for p in PROFILES for q in QUERIES for c in CONCURRENCIES]
        rng.shuffle(block)
        plan += block
    annex = [_run(e, p, "Q2", c, rep, "annex")
             for e in ENGINES for p, c in cells for rep in range(1, repetitions + 1)]
    rng.shuffle(annex)
    return plan + annex


def extend_plan(current, target):
    """Agrega las corridas que faltan sin alterar las ya planificadas."""
    known = {r["id"] for r in current}
    return current + [r for r in target if r["id"] not in known]


class Journal:
    """Registro append-only: es la única fuente de verdad de dónde se quedó la campaña."""

    def __init__(self, path):
        self.path = path

    def append(self, event, **fields):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"ts": time.time(), "event": event, **fields}, ensure_ascii=False)
        with self.path.open("a") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def read(self):
        if not self.path.exists():
            return []
        events = []
        for line in self.path.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events


@dataclass
class Derived:
    state: str = "new"
    pending: list = field(default_factory=list)
    finished: set = field(default_factory=set)
    suspects: set = field(default_factory=set)
    interrupted: str | None = None
    halt_reason: str | None = None
    incidents: int = 0


STATE_BY_EVENT = {"campaign_started": "running", "resumed": "running", "paused": "paused",
                  "halted": "halted", "done": "done"}


def derive(plan, events):
    d = Derived()
    running = None
    for e in events:
        kind = e["event"]
        d.state = STATE_BY_EVENT.get(kind, d.state)
        if kind == "halted":
            d.halt_reason = e.get("reason")
        elif kind == "incident_opened":
            d.incidents += 1
        elif kind == "run_started":
            running = e["run"]
        elif kind == "run_finished":
            d.finished.add(e["run"])
            running = None
        elif kind == "run_suspect":
            d.suspects.add(e["run"])
            running = None
        elif kind == "run_discarded":
            running = None
    d.interrupted = running
    regular = [r for r in plan if r["id"] not in d.finished and r["id"] not in d.suspects]
    tail = [r for r in plan if r["id"] in d.suspects and r["id"] not in d.finished]
    d.pending = regular + tail
    return d
