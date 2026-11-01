# Contrato del dataset

`synthetic_data_generator.py` debe producir un archivo que cumpla este contrato. `run_benchmarks.sh validate-data` lo comprueba antes de cargar.

## Interfaz

```bash
python synthetic_data_generator.py --n 500000 --seed 42 --format ndjson --out-dir data
```

La misma semilla debe producir el mismo archivo, byte a byte.

## Formato

NDJSON: un documento JSON por línea, sin extended JSON (`$date`, `$oid`).

## Campos

| Campo | Tipo | Regla |
|---|---|---|
| `order_id` | string | UUID en minúsculas y único. Es también la PK `id` en PostgreSQL |
| `timestamp` | string | UTC con formato exacto `YYYY-MM-DDTHH:MM:SSZ` |
| `customer.id`, `tier`, `segment` | string | |
| `customer.geo.country`, `state`, `city`, `zip` | string | Cardinalidad limitada en `country` |
| `customer.geo.coordinates` | array | `[lon, lat]` |
| `items[]` | array | Media ≈3 elementos |
| `items[].sku`, `category`, `brand` | string | Cardinalidad limitada en `category` |
| `items[].qty`, `price`, `tax_pct` | número | Números JSON, nunca strings |
| `items[].discounts` | número o array | |
| `payment.method`, `status`, `transaction_id` | string | `status` incluye `completed` y otros valores |
| `payment.gateway_latency_ms`, `final_total` | número | |
| `payment.totals` | objeto | |
| `metadata.channel`, `user_agent`, `session_id` | string | |
| `metadata.flags` | objeto o array | |

## Distribuciones

- `timestamp` debe cruzar `2026-01-01`, p. ej. de 2025-01-01 a 2026-09-30.
- `payment.status` con alrededor de 70–80 % de `completed`.
- `items[].price` con valores por encima y por debajo de 50.

Sin estas distribuciones, los filtros de Q1 y Q2 no filtrarían nada y las mediciones perderían sentido.

## Por qué el formato de `timestamp` es estricto

Q2 compara `timestamp` como texto en ambos motores. Eso solo equivale a comparar fechas si todas tienen el mismo formato y la misma zona.

## Tamaño

El generador debe informar el tamaño promedio por documento. A ≈1 KB, el dataset ronda 500 MB y cabe en memoria en los tres perfiles, lo que reduce la probabilidad de spill u OOM.
