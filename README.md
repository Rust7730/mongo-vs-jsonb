# Medición de métricas en bases documentales

Contención de CPU y memoria en agregaciones JSON: MongoDB frente a PostgreSQL JSONB. Práctica de Bases de Datos en la Nube, UP Chiapas.

- **Resultados:** `results/mediciones.csv`, 108 corridas con el encabezado del playbook.
- **Anexo de aprendizaje:** `results/anexo_q2_variantes.csv`, segunda variante de Q2 en 54 corridas. No forma parte de la matriz de 36 celdas del playbook ni del cálculo de las métricas.
- **Reporte:** `report/reporte.tex` y `report/reporte_latex.pdf`, con portada. `report/reporte.pdf` es la versión anterior, generada desde Markdown.
- **Evidencia de spill y OOM:** `results/raw/*/spill_evidence.log` y `results/raw/*/oom_evidence.log`.

## Requisitos

Linux con cgroups v2, Docker con Compose y [uv](https://docs.astral.sh/uv/). La asignación de CPUs en `docker-compose.yml` y `benchmark_runner/config.py` supone 12 hilos; ajústala a tu host.

## Reproducir

```bash
uv sync --all-groups
.venv/bin/python synthetic_data_generator.py --n 500000 --seed 42 --format ndjson --out-dir data
./run_benchmarks.sh validate-data
./run_benchmarks.sh load-data
./run_benchmarks.sh doctor
./run_benchmarks.sh start
```

La campaña tarda unas 14 horas y corre como servicio de usuario de systemd.

| Comando | Qué hace |
|---|---|
| `./run_benchmarks.sh status` | Muestra progreso, tiempo restante e incidencias |
| `./run_benchmarks.sh pause` | Termina la corrida actual y libera la PC |
| `./run_benchmarks.sh pause --now` | Aborta la corrida actual; se repite después |
| `./run_benchmarks.sh resume` | Valida el host y continúa donde se quedó |
| `./run_benchmarks.sh run-one ...` | Ejecuta una corrida suelta, para pilotos |

Para ensayar con fases reducidas y estado aparte, antepón `--rehearsal` y usa un fixture: `.venv/bin/python -m tests.fixture_gen 20000 data/fixture.ndjson`.

## Regenerar el reporte

```bash
.venv/bin/python -m analysis.summarize
.venv/bin/python -m analysis.build_report
.venv/bin/python -m analysis.build_latex
```

`analysis.build_latex` genera `report/reporte.tex`, que se compila con `pdflatex` desde `report/` y necesita `report/figuras/`. Son tres pasadas para resolver el índice.

Las sondas complementarias de M2, fuera del CSV, son `analysis.probe_no_limit` y `analysis.probe_buffers`.

## Estructura

| Ruta | Contenido |
|---|---|
| `docker-compose.yml`, `profiles/` | Motores, telemetría y perfiles de recursos |
| `queries/` | Agregaciones de MongoDB y SQL de PostgreSQL |
| `benchmark_runner/` | Clientes de carga, métricas y clasificación de resultados |
| `orchestrator/` | Plan, journal, pausa, incidencias y carga de datos |
| `.claude/agents/incident-fixer.md` | Subagente para fallas de infraestructura |
| `analysis/`, `report/` | Tablas, figuras y reporte |
| `docs/` | Contrato y manifiesto del dataset |

Un OOM, un spill o un error de memoria del motor son resultados y van al CSV. Solo las fallas de infraestructura abren una incidencia.

## Pruebas

```bash
uv run --group dev pytest
```
