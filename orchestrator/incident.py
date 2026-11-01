"""Subagente headless: se lanza solo ante una falla de infraestructura persistente."""
import json
import os
import subprocess
import time

from benchmark_runner.config import ROOT

AGENT_TIMEOUT_S = 900
MAX_ATTEMPTS = 2
MAX_INCIDENTS = 4

TOOLS = [
    "Read", "Grep", "Glob",
    "Edit(orchestrator/**)", "Edit(benchmark_runner/telemetry.py)",
    "Edit(benchmark_runner/engine_stats.py)", "Edit(benchmark_runner/runner.py)",
    "Edit(incidents/**)",
    "Bash(./run_benchmarks.sh doctor*)", "Bash(./run_benchmarks.sh repair-*)",
    "Bash(docker ps*)", "Bash(docker logs *)", "Bash(docker inspect *)", "Bash(df *)", "Bash(free *)",
]


def _capture(cmd):
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    return (out.stdout + out.stderr)[-3000:]


def open_incident(run, fault):
    incident_id = time.strftime("%Y%m%d-%H%M%S")
    directory = ROOT / "incidents" / incident_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "incident.json").write_text(json.dumps({
        "id": incident_id, "run": run, "reason": fault.reason, "detail": fault.detail,
        "docker_ps": _capture(["docker", "ps", "-a", "--format", "{{.Names}} {{.Status}}"]),
        "disk": _capture(["df", "-h", "/"]), "memory": _capture(["free", "-h"]),
    }, indent=1, ensure_ascii=False))
    return incident_id, directory


def agent_command(incident_id):
    override = os.environ.get("BENCH_AGENT_CMD")
    if override:
        return ["sh", "-c", override, "agent", incident_id]
    prompt = (f"Incidencia {incident_id}. Lee incidents/{incident_id}/incident.json, repara la causa "
              f"y escribe incidents/{incident_id}/resolution.md.")
    return ["claude", "-p", prompt, "--agent", "incident-fixer", "--model", "sonnet",
            "--permission-mode", "dontAsk", "--allowedTools", ",".join(TOOLS), "--strict-mcp-config",
            "--setting-sources", "project", "--disable-slash-commands", "--no-session-persistence",
            "--output-format", "json"]


def spawn_agent(incident_id, directory, attempt):
    log = directory / f"agent-{attempt}.json"
    started = time.time()
    try:
        with log.open("w") as out:
            code = subprocess.run(agent_command(incident_id), cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL, timeout=AGENT_TIMEOUT_S).returncode
    except subprocess.TimeoutExpired:
        code = "timeout"
    except OSError as exc:
        code = f"spawn_error: {exc}"
    return {"exit": code, "seconds": round(time.time() - started)}


def commit_fix(incident_id):
    subprocess.run(["git", "add", "--", f"incidents/{incident_id}", "orchestrator", "benchmark_runner"], cwd=ROOT)
    message = (f"fix(campaign): resolve incident {incident_id}\n\n"
               "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n")
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=ROOT)
