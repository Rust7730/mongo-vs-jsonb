from analysis.build_latex import column_widths, convert, inline


def test_inline_escapes_latex_specials_outside_and_inside_code():
    assert inline("45 % & $x_1") == r"45 \% \& \$x\_1"
    assert r"\$group" in inline("`$group`")


def test_inline_keeps_code_inside_bold_and_converts_quotes():
    text = inline('**No usar `work_mem` aquí** "n/d"')
    assert text.startswith(r"\textbf{No usar \code{work\_\allowbreak{}mem} aquí}")
    assert text.endswith("``n/d''")


def test_column_widths_fit_the_page():
    widths = column_widths([["Motor", "Valor"], ["MongoDB", "una descripción bastante larga de la celda"]])
    assert sum(widths) < 1 and widths[1] > widths[0]


def test_numbered_headings_use_latex_numbering_and_annexes_do_not():
    assert r"\section{Resultados}" in convert(["## 3. Resultados"])
    assert r"\section*{Anexo A: algo}" in convert(["## Anexo A: algo"])


def test_figure_takes_its_caption_from_the_next_paragraph():
    out = convert(["![x](figuras/a.png)", "", "**Figura 1.** Texto."])
    assert r"\includegraphics[width=\linewidth]{figuras/a.png}" in out and r"\caption{Texto.}" in out


def test_label_before_a_table_becomes_its_first_row():
    out = convert(["**Título:**", "", "| A | B |", "|---|---|", "| 1 | 2 |"])
    assert out.index(r"\begin{longtable}") < out.index(r"\multicolumn{2}") < out.index(r"\textbf{Título:}")
    assert out.index(r"\textbf{Título:}") < out.index(r"\endfirsthead") < out.index(r"\endhead")
    assert r"\needspace" not in out


def test_long_paragraph_before_a_table_stays_outside_it():
    text = "Un párrafo normal que explica algo y no funciona como rótulo."
    out = convert([text, "", "| A | B |", "|---|---|", "| 1 | 2 |"])
    assert out.index(text) < out.index(r"\begin{longtable}")
    assert r"\multicolumn" not in out


def test_label_before_a_list_cannot_be_split_from_it():
    out = convert(["**Cálculo:**", "", "- uno"])
    assert out.index(r"\nopagebreak") < out.index(r"\begin{itemize}")
