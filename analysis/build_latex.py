"""Convierte report/reporte.md en report/reporte.tex, con portada y las tablas calculadas."""
import math
import re
from pathlib import Path

REPORT = Path(__file__).resolve().parent.parent / "report"

COVER = {"alumno": "Rodolfo Ramirez Reyes", "grupo": "7B", "maestro": "Horacio Irán Solís Cisneros",
         "fecha": "1 de noviembre de 2026"}

PREAMBLE = r"""\documentclass[11pt,letterpaper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[spanish,es-noshorthands,es-nodecimaldot,es-tabla]{babel}
\usepackage{lmodern}
\usepackage[margin=2.5cm]{geometry}
\usepackage{array,booktabs,longtable}
\usepackage{graphicx,float}
\usepackage[font=small,labelfont=bf]{caption}
\usepackage{enumitem}
\usepackage{listings}
\usepackage{xcolor}
\usepackage[hidelinks]{hyperref}

\setlength{\parskip}{0.5em}
\setlength{\parindent}{0pt}
\setlength{\LTleft}{0pt}
\setlength{\LTright}{0pt}
\setlength{\emergencystretch}{3em}
\setlist{itemsep=0.2em,topsep=0.2em}
\lstset{basicstyle=\ttfamily\footnotesize,breaklines=true,backgroundcolor=\color{black!5},frame=none,
        columns=fullflexible,keepspaces=true}
\newcommand{\code}[1]{\texttt{#1}}

\begin{document}
"""

TITLE_PAGE = r"""\begin{titlepage}
\centering
{\Large\bfseries Universidad Politécnica de Chiapas\par}
\vspace{0.4cm}
{\large Ingeniería en Tecnologías de la Información e Innovación Digital\par}
\vspace{2.5cm}
{\LARGE\bfseries %(title)s\par}
\vspace{0.8cm}
{\large %(subtitle)s\par}
\vfill
\begin{tabular}{rl}
\textbf{Materia:} & Bases de Datos en la Nube \\[0.3em]
\textbf{Alumno:} & %(alumno)s \\[0.3em]
\textbf{Grupo:} & %(grupo)s \\[0.3em]
\textbf{Maestro:} & %(maestro)s \\[0.3em]
\textbf{Fecha:} & %(fecha)s \\
\end{tabular}
\vspace{2cm}
\end{titlepage}

\tableofcontents
\newpage

"""

SPECIALS = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
            "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def escape(text):
    return "".join(SPECIALS.get(ch, ch) for ch in text)


def code_span(text):
    body = escape(text)
    for mark, replacement in ((r"\_", r"\_\allowbreak{}"), ("/", r"/\allowbreak{}"), (".", r".\allowbreak{}")):
        body = body.replace(mark, replacement)
    return rf"\code{{{body}}}"


def inline(text):
    spans = []

    def stash(match):
        spans.append(code_span(match[1]))
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = escape(text)
    text = re.sub(r'"([^"]+)"', r"``\1''", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    return re.sub("\x00(\\d+)\x00", lambda m: spans[int(m[1])], text)


def strip_spans(cell):
    return re.sub(r"[`*]", "", cell)


def column_widths(rows):
    weights = []
    for column in zip(*rows):
        cells = [strip_spans(c) for c in column]
        longest_word = max(len(word) for c in cells for word in c.split() or [""])
        weights.append(max(longest_word + 1.5, max(len(c) for c in cells) ** 0.75))
    return [0.995 * w / sum(weights) for w in weights]


def table(lines, label=None):
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in lines]
    header, body = rows[0], rows[2:]
    spec = "".join(rf">{{\raggedright\arraybackslash}}p{{\dimexpr{w:.3f}\linewidth-2\tabcolsep\relax}}"
                   for w in column_widths([header] + body))
    head = " & ".join(rf"\textbf{{{inline(c)}}}" for c in header)
    columns = [r"\toprule", rf"{head} \\", r"\midrule"]
    first = [rf"\multicolumn{{{len(header)}}}{{@{{}}l}}{{\normalsize {inline(label)}}} \\[0.4em]"] if label else []
    out = [r"{\footnotesize\setlength{\tabcolsep}{3pt}", rf"\begin{{longtable}}{{{spec}}}", *first, *columns,
           r"\endfirsthead", *columns, r"\endhead"]
    out += [" & ".join(inline(c) for c in row) + r" \\" for row in body]
    out += [r"\bottomrule", r"\end{longtable}}", ""]
    return "\n".join(out)


def figure(path, caption):
    return (f"\\begin{{figure}}[H]\n\\centering\n\\includegraphics[width=\\linewidth]{{{path}}}\n"
            f"\\caption{{{inline(caption)}}}\n\\end{{figure}}\n")


def heading(level, text):
    if level == 3:
        return rf"\subsection{{{inline(text)}}}"
    numbered = re.match(r"\d+\.\s+(.*)", text)
    if numbered:
        return rf"\section{{{inline(numbered[1])}}}"
    return rf"\section*{{{inline(text)}}}" + "\n" + rf"\addcontentsline{{toc}}{{section}}{{{inline(text)}}}"


def convert(lines):
    out, i, label = [], 0, None
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("```"):
            end = next(j for j in range(i + 1, len(lines)) if lines[j].startswith("```"))
            out.append("\\begin{lstlisting}\n" + "\n".join(lines[i + 1:end]) + "\n\\end{lstlisting}\n")
            i = end + 1
        elif match := re.match(r"(#{2,3}) (.*)", line):
            out.append(heading(len(match[1]), match[2]) + "\n")
            i += 1
        elif line.startswith("|"):
            end = i
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            out.append(table(lines[i:end], label))
            label = None
            i = end
        elif match := re.match(r"!\[.*?\]\((.*?)\)", line):
            caption = re.match(r"\*\*Figura \d+\.\*\* (.*)", lines[i + 2])
            out.append(figure(match[1], caption[1]))
            i += 3
        elif re.match(r"(- |\d+\. )", line):
            environment = "itemize" if line.startswith("- ") else "enumerate"
            items = []
            while i < len(lines) and re.match(r"(- |\d+\. )", lines[i]):
                items.append(r"\item " + inline(re.sub(r"^(- |\d+\. )", "", lines[i])))
                i += 1
            out.append(rf"\begin{{{environment}}}" + "\n" + "\n".join(items) + "\n" + rf"\end{{{environment}}}" + "\n")
        else:
            following = next((l for l in lines[i + 1:] if l.strip()), "")
            if line.endswith(":**") and following.startswith("|"):
                label = line
            else:
                suffix = "\n\\nopagebreak" if line.endswith(":**") else ""
                out.append(inline(line) + suffix + "\n")
            i += 1
    return "\n".join(out)


def main():
    text = (REPORT / "reporte.md").read_text()
    text = re.sub(r"\{\{tabla:(\w+)\}\}", lambda m: (REPORT / "tablas" / f"{m[1]}.md").read_text(), text)
    lines = text.splitlines()
    title = lines[0].removeprefix("# ")
    subtitle = lines[2].strip("*")
    start = next(i for i, line in enumerate(lines) if line.startswith("## "))
    cover = TITLE_PAGE % {"title": inline(title), "subtitle": inline(subtitle), **COVER}
    (REPORT / "reporte.tex").write_text(PREAMBLE + cover + convert(lines[start:]) + "\n\\end{document}\n")


if __name__ == "__main__":
    main()
