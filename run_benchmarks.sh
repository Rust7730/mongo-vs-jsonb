#!/usr/bin/env bash
# Automatiza la matriz de mediciones.
#   ./run_benchmarks.sh {start|pause [--now]|resume|status|doctor}
#   ./run_benchmarks.sh validate-data|load-data [--file ruta]
#   ./run_benchmarks.sh run-one --engine E --profile P --query Q --concurrency C
#   ./run_benchmarks.sh --rehearsal <comando>   ensayo con fases reducidas y estado aparte
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
if [[ "${1:-}" == "--rehearsal" ]]; then
  shift
  export BENCH_REHEARSAL=1 BENCH_STATE_DIR=state-rehearsal BENCH_RESULTS_DIR=results-rehearsal
  export BENCH_PHASE_SCALE="${BENCH_PHASE_SCALE:-0.05}" BENCH_DATA="${BENCH_DATA:-data/fixture.ndjson}"
fi
exec .venv/bin/python -m orchestrator.cli "$@"
