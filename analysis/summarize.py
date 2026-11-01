"""Genera las tablas y figuras del reporte. Las repeticiones se resumen con la mediana."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS, REPORT = ROOT / "results", ROOT / "report"
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLORS = {"mongodb": "#2a78d6", "postgresql": "#eb6834"}
NAMES = {"mongodb": "MongoDB", "postgresql": "PostgreSQL"}
MARKERS = {"mongodb": "o", "postgresql": "s"}
PROFILE_MARKERS = {"A": "o", "B": "s", "C": "^"}
LIMITS_MB = {"A": 4096, "B": 2048, "C": 1024}
DOCS_DATASET = 500_000
# Documentos leídos por ejecución, de executionStats y EXPLAIN (results/explain).
DOCS_READ = {("mongodb", "Q1"): 500_000, ("postgresql", "Q1"): 500_000,
             ("mongodb", "Q2"): 226_680, ("postgresql", "Q2"): 500_000}

plt.rcParams.update({"font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "text.color": INK, "axes.facecolor": SURFACE, "figure.facecolor": SURFACE,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.7, "axes.axisbelow": True, "savefig.dpi": 170})


def load():
    df = pd.read_csv(RESULTS / "mediciones.csv")
    df["p"] = df.profile.str[8]
    metas = []
    for path in (RESULTS / "raw").glob("*/meta.json"):
        m = json.loads(path.read_text())
        run = m["run"]
        metas.append({"engine": run["engine"], "query_id": run["query"], "p": run["profile"],
                      "concurrency": run["concurrency"], "run_number": run["rep"], "variant": run["variant"],
                      "n": m["signals"]["completed"], "cpu_s": m["cpu_seconds"], "written_mb": m["written_bytes"] / 2**20,
                      "shmem_mb": m["shmem_final"] / 2**20, "peak_mb": m["memory_peak_bytes"] / 2**20})
    meta = pd.DataFrame(metas)
    strict = meta[meta.variant == "strict"].drop(columns="variant")
    return df.merge(strict, on=["engine", "query_id", "p", "concurrency", "run_number"]), meta


KEYS = ["engine", "query_id", "p", "concurrency"]


def cells(df):
    g = df.groupby(KEYS)
    out = g[["throughput_qps", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms", "cpu_throttled_seconds",
             "max_rss_mb", "n", "written_mb", "cpu_s"]].median()
    out["spill"] = g.disk_spill.sum()
    out["status"] = g.status.agg(lambda s: "/".join(sorted(set(s))))
    return out.reset_index()


def seconds(ms):
    return "n/d" if pd.isna(ms) else f"{ms / 1000:.2f}"


def md_table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def table_results(c):
    rows = [(NAMES[r.engine], r.query_id, r.p, r.concurrency, f"{r.throughput_qps:.2f}", seconds(r.latency_p50_ms),
             seconds(r.latency_p95_ms), seconds(r.latency_p99_ms), f"{r.cpu_throttled_seconds:.0f}",
             f"{r.max_rss_mb:.0f}", int(r.n), r.status) for r in c.itertuples()]
    return md_table(["Motor", "Query", "Perfil", "Clientes", "QPS", "P50 (s)", "P95 (s)", "P99 (s)", "Throttling (s)",
                     "RSS máx (MB)", "n", "Estado"], rows)


def table_contention(c):
    rows = []
    for (engine, query, conc), g in c.groupby(["engine", "query_id", "concurrency"]):
        by = g.set_index("p")
        a, b, z = by.loc["A"], by.loc["B"], by.loc["C"]
        ratio = lambda x: "OOM" if pd.isna(x.latency_p99_ms) else f"×{x.latency_p99_ms / a.latency_p99_ms:.1f}"
        rows.append((NAMES[engine], query, conc, seconds(a.latency_p99_ms), ratio(b), ratio(z)))
    return md_table(["Motor", "Query", "Clientes", "P99 perfil A (s)", "P99 B vs A", "P99 C vs A"], rows)


def table_footprint(df):
    d = df[df.n > 0].copy()
    d["docs"] = [DOCS_READ[(e, q)] * n / 1000 for e, q, n in zip(d.engine, d.query_id, d.n)]
    d["cpu_ms_1k"] = d.cpu_s * 1000 / d.docs
    d["rss_kb_1k"] = d.max_rss_mb * 1024 / (DOCS_DATASET / 1000)
    g = d[d.concurrency.isin([1, 50])].groupby(KEYS)[["cpu_ms_1k", "rss_kb_1k"]].median().reset_index()
    rows = [(NAMES[r.engine], r.query_id, r.p, r.concurrency, f"{r.cpu_ms_1k:.2f}", f"{r.rss_kb_1k:.0f}")
            for r in g.itertuples()]
    return md_table(["Motor", "Query", "Perfil", "Clientes", "CPU (ms / 1000 docs leídos)",
                     "RSS máx (KB / 1000 docs del dataset)"], rows)


def table_annex(c):
    annex = pd.read_csv(RESULTS / "anexo_q2_variantes.csv")
    annex["p"] = annex.profile.str[8]
    annex = annex.groupby(["engine", "p", "concurrency"])[["throughput_qps", "latency_p99_ms"]].median()
    official = c[c.query_id == "Q2"].set_index(["engine", "p", "concurrency"])
    rows = []
    for (engine, p, conc), r in annex.iterrows():
        o = official.loc[(engine, p, conc)]
        rows.append((NAMES[engine], p, conc, f"{o.throughput_qps:.2f}", f"{r.throughput_qps:.2f}",
                     f"×{r.throughput_qps / o.throughput_qps:.2f}", seconds(o.latency_p99_ms), seconds(r.latency_p99_ms),
                     f"×{r.latency_p99_ms / o.latency_p99_ms:.2f}"))
    return md_table(["Motor", "Perfil", "Clientes", "QPS oficial", "QPS anexo", "QPS anexo / oficial", "P99 oficial (s)",
                     "P99 anexo (s)", "P99 anexo / oficial"], rows)


def fig_p99(c):
    fig, axes = plt.subplots(2, 3, figsize=(8.2, 5.2), sharex=True, sharey=True)
    x = {1: 0, 10: 1, 50: 2}
    for i, query in enumerate(("Q1", "Q2")):
        for j, profile in enumerate("ABC"):
            ax = axes[i][j]
            for engine, color in COLORS.items():
                g = c[(c.engine == engine) & (c.query_id == query) & (c.p == profile)].sort_values("concurrency")
                ok = g.dropna(subset=["latency_p99_ms"])
                ax.plot([x[v] for v in ok.concurrency], ok.latency_p99_ms / 1000, color=color, lw=2,
                        marker=MARKERS[engine], ms=7, mec=SURFACE, mew=1.5)
                for r in g[g.latency_p99_ms.isna()].itertuples():
                    ax.annotate("OOM", (x[r.concurrency], 0.5), xycoords=("data", "axes fraction"), ha="center",
                                fontsize=9, fontweight="bold", color=INK)
            ax.set_yscale("log")
            ax.set_title(f"{query} · perfil {profile}", loc="left", fontsize=9, color=INK)
            ax.set_xticks([0, 1, 2], ["1", "10", "50"])
            ax.set_xlim(-0.25, 2.25)
            ax.grid(axis="x", visible=False)
    for ax in axes[1]:
        ax.set_xlabel("Clientes concurrentes")
    for row in axes:
        row[0].set_ylabel("P99 (s, escala log)")
    handles = [Line2D([], [], color=COLORS[e], marker=MARKERS[e], lw=2, ms=7, label=NAMES[e]) for e in COLORS]
    fig.legend(handles=handles, loc="upper right", ncol=2, frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(REPORT / "figuras" / "p99_vs_concurrencia.png")


def fig_throttling(c):
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.6), sharey=True)
    data = c.dropna(subset=["latency_p99_ms"])
    for ax, query in zip(axes, ("Q1", "Q2")):
        for r in data[data.query_id == query].itertuples():
            ax.scatter(r.cpu_throttled_seconds, r.throughput_qps, s=46, color=COLORS[r.engine],
                       marker=PROFILE_MARKERS[r.p], edgecolors=SURFACE, linewidths=1)
        ax.set_yscale("log")
        ax.set_title(query, loc="left", fontsize=9, color=INK)
        ax.set_xlabel("CPU throttling en la ventana de 300 s (s)")
    axes[0].set_ylabel("Throughput (QPS, escala log)")
    handles = [Line2D([], [], ls="", marker="o", ms=7, color=COLORS[e], label=NAMES[e]) for e in COLORS]
    handles += [Line2D([], [], ls="", marker=m, ms=7, color=MUTED, label=f"Perfil {p}") for p, m in PROFILE_MARKERS.items()]
    fig.legend(handles=handles, loc="upper right", ncol=5, frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(REPORT / "figuras" / "throttling_vs_qps.png")


def rss_series(engine, profile):
    path = RESULTS / "raw" / f"{engine}-{profile}-Q1-c50-r1" / "series.csv"
    rows = list(csv.DictReader(path.open()))
    t0 = float(rows[0]["t"])
    return [float(r["t"]) - t0 for r in rows], [int(r["anon"]) / 2**20 for r in rows]


def fig_rss():
    fig, axes = plt.subplots(1, 3, figsize=(8.2, 3.3), sharey=True)
    for ax, profile in zip(axes, "ABC"):
        for engine, color in COLORS.items():
            t, rss = rss_series(engine, profile)
            ax.plot(t, rss, color=color, lw=1.6)
        ax.axhline(LIMITS_MB[profile], color=MUTED, lw=1, ls="--")
        ax.text(415, LIMITS_MB[profile] * 1.03, f"Límite {LIMITS_MB[profile]} MB", ha="right", color=MUTED, fontsize=8)
        ax.set_title(f"Perfil {profile}", loc="left", fontsize=9, color=INK)
        ax.set_xlabel("Tiempo desde el warmup (s)")
        ax.set_ylim(0, 4600)
    axes[0].set_ylabel("RSS del contenedor (MB)")
    handles = [Line2D([], [], color=COLORS[e], lw=2, label=NAMES[e]) for e in COLORS]
    fig.legend(handles=handles, loc="upper right", ncol=2, frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(REPORT / "figuras" / "curva_rss.png")


def main():
    df, _ = load()
    c = cells(df)
    tables = {"resultados": table_results(c), "contencion": table_contention(c), "huella": table_footprint(df),
              "anexo": table_annex(c)}
    for name, text in tables.items():
        (REPORT / "tablas" / f"{name}.md").write_text(text)
    fig_p99(c)
    fig_throttling(c)
    fig_rss()
    return c, tables


if __name__ == "__main__":
    _, generated = main()
    for key in ("contencion", "huella", "anexo"):
        print(generated[key])
