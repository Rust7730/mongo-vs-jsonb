"""Inserta las tablas en report/reporte.md y exporta report/reporte.pdf."""
import re
from pathlib import Path

import markdown
from weasyprint import HTML

REPORT = Path(__file__).resolve().parent.parent / "report"
CSS = """
@page { size: Letter; margin: 2cm 1.8cm; @bottom-center { content: counter(page); font-size: 8pt; color: #52514e; } }
body { font-family: 'DejaVu Sans', sans-serif; font-size: 9.5pt; line-height: 1.45; color: #0b0b0b; }
h1 { font-size: 20pt; margin: 0 0 6pt; }
h2 { font-size: 13pt; margin: 18pt 0 6pt; page-break-after: avoid; }
h3 { font-size: 10.5pt; margin: 12pt 0 4pt; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; font-size: 8pt; margin: 6pt 0 10pt; }
th { text-align: left; border-bottom: 1px solid #52514e; padding: 3pt 4pt; }
td { border-bottom: 0.5px solid #e4e3df; padding: 2.5pt 4pt; }
tr { page-break-inside: avoid; }
thead { display: table-header-group; }
img { width: 100%; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 8.5pt; }
pre { background: #f3f2ee; padding: 6pt; font-size: 7.5pt; white-space: pre-wrap; }
"""


def main():
    text = (REPORT / "reporte.md").read_text()
    text = re.sub(r"\{\{tabla:(\w+)\}\}", lambda m: (REPORT / "tablas" / f"{m[1]}.md").read_text(), text)
    body = markdown.markdown(text, extensions=["tables", "fenced_code"])
    html = f"<html lang='es'><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"
    HTML(string=html, base_url=str(REPORT)).write_pdf(REPORT / "reporte.pdf")


if __name__ == "__main__":
    main()
