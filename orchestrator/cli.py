"""Interfaz de run_benchmarks.sh. Nada aquí consume tokens."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from benchmark_runner.config import (CONCURRENCIES, DATA_PATH, ENGINES, PROFILES, QUERIES, REHEARSAL, RESULTS_DIR,
                                     ROOT, STATE_DIR, VARIANTS)

from . import dataload, explain, host, manifest, preflight
from .state import Journal, build_plan, derive, extend_plan

SEED = 20261030
UNIT = "bench-rehearsal" if REHEARSAL else "bench-campaign"


def journal():
    return Journal(STATE_DIR / "journal.jsonl")


def plan():
    path = STATE_DIR / "plan.json"
    return json.loads(path.read_text()) if path.exists() else []


def service_active():
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", UNIT]).returncode == 0


def launch():
    env = [f"--setenv={k}={v}" for k, v in os.environ.items() if k.startswith("BENCH_") or k in ("PATH", "HOME")]
    subprocess.run(["systemctl", "--user", "reset-failed", UNIT], capture_output=True)
    log = ROOT / STATE_DIR.name / "campaign.log"
    subprocess.run(["systemd-run", "--user", f"--unit={UNIT}", "--collect", "--same-dir", *env,
                    f"--property=StandardOutput=append:{log}", f"--property=StandardError=append:{log}",
                    "systemd-inhibit", "--what=sleep:idle", "--who=practica-bd", "--why=Campaña de benchmark",
                    "--mode=block", str(ROOT / ".venv/bin/python"), "-m", "orchestrator.campaign"], check=True)


def require_clean_host():
    failed = [c for c in preflight.checks() if not c[1]]
    for name, _, detail in failed:
        print(f"✗ {name}: {detail}")
    if failed:
        sys.exit(1)


def save_host_spec():
    """Registra el entorno al arrancar, para la sección 1 del reporte."""
    commands = ["uname -srm", "lscpu", "free -h", "swapon --show", "docker version", "docker compose version",
                "docker info --format 'cgroup v{{.CgroupVersion}}, driver {{.CgroupDriver}}, storage {{.Driver}}'",
                "docker compose config --images"]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with (RESULTS_DIR / "host_spec.txt").open("w") as out:
        for command in commands:
            result = subprocess.run(command, shell=True, cwd=ROOT, capture_output=True, text=True)
            out.write(f"$ {command}\n{result.stdout}{result.stderr}\n")


def cmd_start(args):
    if plan() and journal().read():
        sys.exit("Ya existe una campaña. Usa resume.")
    require_clean_host()
    repetitions = 1 if REHEARSAL else 3
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "plan.json").write_text(json.dumps(build_plan(SEED, repetitions), indent=1))
    manifest.save(STATE_DIR / "manifest.json", DATA_PATH)
    save_host_spec()
    launch()
    print(f"Campaña iniciada: {len(plan())} corridas.")


def cmd_resume(args):
    if service_active():
        sys.exit("La campaña ya está corriendo.")
    if not derive(plan(), journal().read()).pending:
        sys.exit("La campaña ya terminó.")
    require_clean_host()
    (STATE_DIR / "control").unlink(missing_ok=True)
    launch()
    print("Campaña reanudada.")


def cmd_extend_plan(args):
    """Completa la segunda variante de Q2. Conserva el avance y no toca el CSV oficial."""
    if service_active():
        sys.exit("Pausa la campaña antes de ampliar el plan.")
    current = plan()
    extended = extend_plan(current, build_plan(SEED, 1 if REHEARSAL else 3))
    (STATE_DIR / "plan.json").write_text(json.dumps(extended, indent=1))
    journal().append("plan_extended", added=len(extended) - len(current))
    print(f"Plan: {len(current)} → {len(extended)} corridas.")


def cmd_pause(args):
    if not service_active():
        sys.exit("No hay campaña en ejecución.")
    (STATE_DIR / "control").write_text("pause_now" if args.now else "pause")
    print("Abortando la corrida actual." if args.now else "Se pausará al terminar la corrida actual.")


def cmd_status(args):
    events, runs = journal().read(), plan()
    d = derive(runs, events)
    starts = {}
    durations = []
    current = None
    for e in events:
        if e["event"] == "run_started":
            starts[e["run"]] = e["ts"]
            current = e["run"]
        elif e["event"] == "run_finished" and e["run"] in starts:
            durations.append(e["ts"] - starts[e["run"]])
            current = None
    average = sum(durations) / len(durations) if durations else 465
    state = d.state
    if state == "running" and not service_active():
        state = "interrumpida (usa resume)"
    print(f"Estado:      {state}")
    print(f"Progreso:    {len(d.finished)}/{len(runs)} corridas")
    print(f"Restante:    ≈{len(d.pending) * average / 3600:.1f} h")
    if current and service_active():
        print(f"Corrida:     {current}")
    if d.suspects:
        print(f"Sospechosas: {len(d.suspects)}")
    print(f"Incidencias: {d.incidents}")
    if d.halt_reason:
        print(f"Motivo:      {d.halt_reason}")


def cmd_doctor(args):
    for name, ok, detail in preflight.checks():
        print(f"{'✓' if ok else '✗'} {name}" + (f": {detail}" if not ok and detail else ""))
    print(subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"],
                         capture_output=True, text=True).stdout)


def cmd_wait_end(args):
    """Bloquea sin consumir tokens; solo termina cuando hay algo que atender."""
    while True:
        d = derive(plan(), journal().read())
        state = d.state
        if state == "halted" or (state == "done" and not d.pending):
            print(state)
            return
        if state == "running" and not service_active():
            time.sleep(10)
            if derive(plan(), journal().read()).state == "running" and not service_active():
                print("interrupted")
                return
        time.sleep(30)


def cmd_validate(args):
    report = dataload.validate(Path(args.file) if args.file else DATA_PATH)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    if report["errors"]:
        sys.exit(1)


def load(path):
    report = dataload.validate(path)
    if report["errors"]:
        sys.exit("Dataset inválido:\n" + "\n".join(report["errors"]))
    host.stop_engines()
    host.start_engine("mongodb", "A")
    host.wait_ready("mongodb")
    mongo = dataload.load_mongo(path)
    host.stop_engines()
    host.start_engine("postgresql", "A")
    host.wait_ready("postgresql")
    pg = dataload.load_pg(path)
    host.stop_engines()
    if not dataload.same_dataset(mongo, pg):
        sys.exit(f"Los motores no coinciden: {mongo} vs {pg}")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "dataset.json").write_text(json.dumps({**pg, "avg_doc_bytes": report["avg_doc_bytes"],
                                                        "source": str(path)}, indent=1))
    print(json.dumps({"mongodb": mongo, "postgresql": pg}, indent=1))


def cmd_load(args):
    load(Path(args.file).resolve() if args.file else DATA_PATH)


def cmd_repair_telemetry(args):
    host.recreate_telemetry()


def cmd_repair_engines(args):
    host.stop_engines()


def cmd_repair_reload(args):
    load(DATA_PATH)


def cmd_run_one(args):
    """Corrida suelta para el piloto: no toca el plan, el journal ni el CSV oficial."""
    from benchmark_runner.csvout import append_row
    from benchmark_runner.runner import execute

    run = {"id": f"{args.engine}-{args.profile}-{args.query}-c{args.concurrency}-{args.variant}-{int(time.time())}",
           "engine": args.engine, "profile": args.profile, "query": args.query,
           "concurrency": args.concurrency, "rep": 1, "variant": args.variant}
    out = RESULTS_DIR / "pilot"
    host.start_telemetry()
    host.stop_engines()
    host.drop_caches()
    host.start_engine(args.engine, args.profile)
    host.wait_ready(args.engine)
    outcome = execute(run, out / run["id"], lambda: False)
    (out / f"{run['id']}.plan.txt").write_text(explain.explain(args.engine, args.query, args.variant))
    host.stop_engines()
    append_row(out / f"pilot-{run['id']}.csv", outcome.row)
    print(json.dumps({**outcome.row, "fault": outcome.fault, "reason": outcome.reason}, indent=1))


def main():
    parser = argparse.ArgumentParser(prog="run_benchmarks.sh")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("start", cmd_start), ("resume", cmd_resume), ("status", cmd_status),
                          ("doctor", cmd_doctor), ("wait-end", cmd_wait_end), ("extend-plan", cmd_extend_plan),
                          ("repair-telemetry", cmd_repair_telemetry), ("repair-engines", cmd_repair_engines),
                          ("repair-reload-data", cmd_repair_reload)):
        sub.add_parser(name).set_defaults(handler=handler)
    pause = sub.add_parser("pause")
    pause.add_argument("--now", action="store_true")
    pause.set_defaults(handler=cmd_pause)
    for name, handler in (("validate-data", cmd_validate), ("load-data", cmd_load)):
        p = sub.add_parser(name)
        p.add_argument("--file")
        p.set_defaults(handler=handler)
    one = sub.add_parser("run-one")
    one.add_argument("--engine", choices=ENGINES, required=True)
    one.add_argument("--profile", choices=list(PROFILES), required=True)
    one.add_argument("--query", choices=QUERIES, required=True)
    one.add_argument("--concurrency", type=int, choices=CONCURRENCIES, required=True)
    one.add_argument("--variant", choices=list(VARIANTS), default="strict")
    one.set_defaults(handler=cmd_run_one)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
