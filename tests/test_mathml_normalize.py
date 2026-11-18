import xml.etree.ElementTree as ET

import pytest
from latex2mathml.converter import convert

from formula_ocr.mathml_normalize import convert_mathml, _font_safe_source


NS = {"m": "http://www.w3.org/1998/Math/MathML"}


def tree(latex, **kwargs):
    return ET.fromstring(convert_mathml(latex, display="block", **kwargs))


def text(root):
    return "".join(root.itertext())


@pytest.mark.parametrize("environment,open_,close_", [
    ("pmatrix", "(", ")"), ("bmatrix", "[", "]"), ("Bmatrix", "{", "}"),
    ("vmatrix", "|", "|"), ("Vmatrix", "\u2016", "\u2016"),
    ("bmatrix*", "[", "]"),
])
@pytest.mark.parametrize("script,tag,arity", [("^T", "msup", 2), ("_i", "msub", 2), ("_i^T", "msubsup", 3)])
def test_fenced_matrix_is_one_script_operand(environment, open_, close_, script, tag, arity):
    alignment = "[r]" if environment.endswith("*") else ""
    root = tree(r"\begin{" + environment + "}" + alignment + r"a&b\\c&d\end{" + environment + "}" + script)
    scripted = root.find(".//m:" + tag, NS)
    assert len(scripted) == arity
    base = scripted[0]
    assert base.tag.endswith("}mrow") and len(base) == 3
    assert base[0].text == open_ and base[2].text == close_
    assert len(base.findall("m:mtable/m:mtr", NS)) == 2
    assert [text(c) for c in base.findall("m:mtable/m:mtr/m:mtd", NS)] == ["a", "b", "c", "d"]


def test_adjacent_and_nested_matrix_fences_stay_independent():
    root = tree(r"\begin{bmatrix}a\\b\end{bmatrix}\begin{pmatrix}\begin{vmatrix}c&d\\e&f\end{vmatrix}\\g\end{pmatrix}^T+x_i^2")
    assert len(root.findall(".//m:mtable", NS)) == 3
    assert text(root) == "[ab](|cdef|g)T+xi2"
    assert all(len(n) == 2 for n in root.findall(".//m:msup", NS))
    assert len(root.find(".//m:msubsup", NS)) == 3


@pytest.mark.parametrize("latex", [
    r"(a+b)^2+[x]_i", r"\left(\frac{a}{b}\right)^{n+1}",
    r"\frac{x_i^2}{\sqrt[3]{y}}", r"\begin{matrix}a&b\\c&d\end{matrix}^T",
    r"\begin{array}{rl}a&b\\c&d\end{array}", r"\mathsf{P}+\mathbf{F}+\mathcal{L}+\boldsymbol{u}",
])
def test_unaffected_formulas_remain_byte_identical(latex):
    assert convert_mathml(latex, display="block") == convert(latex, display="block")


@pytest.mark.parametrize("letter", ["d", "T", "P", "a", "Z"])
def test_compact_mathrm_keeps_explicit_normal_font(letter):
    root = tree(r"x+\mathrm{" + letter + r"}+y_i^{\mathrm{T}}")
    normal = root.findall('.//m:mi[@mathvariant="normal"]', NS)
    assert [n.text for n in normal] == [letter, "T"]
    assert root.find('.//m:mi[.="x"]', NS).get("mathvariant") is None


def test_font_scope_and_semantic_alphabets_are_preserved():
    root = tree(r"\mathrm{d}+d+\mathsf{P}+\mathbf{F}+\mathcal{L}+\mathrm{ab\mathit{x}}")
    assert "\U0001d5af" in text(root)  # sans-serif P / Ferrers
    assert "\U0001d405" in text(root)  # bold F / Olver
    assert "\u2112" in text(root)
    assert [n.text for n in root.findall('.//m:mi[@mathvariant="normal"]', NS)][:3] == ["d", "a", "b"]
    assert "\U0001d465" in text(root)  # inner mathit keeps its italic Unicode x


@pytest.mark.parametrize("latex", [r"\text{\mathrm{d}}", r"\verb|\mathrm{d}|", r"\\mathrm{d}", "% \\mathrm{d}\nx"])
def test_font_fix_does_not_rewrite_text_comments_or_escaped_commands(latex):
    assert _font_safe_source(latex) == latex


def test_e05_nested_alignment_spacing_does_not_pollute_formula():
    latex = r"\begin{align*}\mathbf{m}'&=\begin{pmatrix}a\\b\end{pmatrix},\\[6pt]\mathbf{P}'&=\begin{pmatrix}c&d\\e&f\end{pmatrix}.\end{align*}"
    root = tree(latex)
    outer, first, second = root.findall(".//m:mtable", NS)
    assert outer.get("rowspacing") == "9pt"
    assert "6pt" not in text(root)
    assert len(outer.findall("m:mtr", NS)) == 2
    assert first.get("rowspacing") is None and second.get("rowspacing") is None
    assert all("style" not in n.attrib for n in root.iter())
    preview = tree(latex, for_preview=True)
    cells = preview.find(".//m:mtable/m:mtr", NS).findall("m:mtd", NS)
    assert all("calc(3pt + 6pt)" in c.get("style", "") for c in cells)


def test_p34_cases_with_two_extra_gaps_keep_three_rows_and_conditions():
    root = tree(r"D=\begin{cases}\frac{i}{p^2}&a=0\\[6pt]\frac{i}{q^2}&b\ne0\\[6pt]0&\text{otherwise}\end{cases}", for_preview=True)
    table = root.find(".//m:mtable", NS)
    assert len(table) == 3
    assert "6pt" not in text(root)
    assert text(table[-1]) == "0otherwise"
    assert table.get("rowspacing") == "6pt 6pt"  # portable mixed-unit fallback
    assert "calc(1ex + 6pt)" in table[0][0].get("style", "")


@pytest.mark.parametrize("length,gap", [("-2pt", "1pt"), ("-20pt", "0pt"), ("+2.5pt", "5.5pt"), ("0", "3pt")])
def test_signed_extra_spacing_and_zero(length, gap):
    root = tree(r"\begin{align*}a&=b\\[" + length + r"]c&=d\end{align*}")
    assert text(root) == "a=bc=d"
    assert root.find(".//m:mtable", NS).get("rowspacing") == gap


def test_negative_mixed_units_preserve_exact_preview_adjustment():
    root = tree(r"\begin{cases}a&x\\[-.5em]b&y\end{cases}", for_preview=True)
    table = root.find(".//m:mtable", NS)
    assert text(root) == "{axby"
    assert table.get("rowspacing") == "0pt"
    assert "calc(1ex - 0.5em)" in table[0][0].get("style", "")


@pytest.mark.parametrize("latex,expected", [
    (r"[6pt]+x", "[6pt]+x"),
    (r"\begin{matrix}a+[6pt]\\b\end{matrix}", "a+[6pt]b"),
    (r"\begin{matrix}a\\{}[6pt]b\end{matrix}", "a[6pt]b"),
    (r"\begin{matrix}a\\[x]b\end{matrix}", "a[x]b"),
    (r"\begin{matrix}a\\[3]b\end{matrix}", "a[3]b"),
    (r"\begin{matrix}a\cr[6pt]b\end{matrix}", "a[6pt]b"),
])
def test_only_optional_length_at_a_row_break_is_consumed(latex, expected):
    assert text(tree(latex)) == expected


def test_row_lengths_do_not_leak_across_nested_matrices():
    root = tree(r"\begin{align*}A&=\begin{bmatrix}a\\[2pt]b\end{bmatrix}\\[6pt]B&=c\\d&=e\end{align*}")
    outer, inner = root.findall(".//m:mtable", NS)
    assert outer.get("rowspacing") == "9pt 3pt"
    assert inner.get("rowspacing") == "2pt"
    assert "pt" not in text(root)


def test_starred_row_break_and_trailing_break_do_not_add_formula_tokens():
    root = tree(r"\begin{matrix}a\\*[2pt]b\\[1pt]\end{matrix}")
    assert text(root) == "ab"
    assert len(root.find(".//m:mtable", NS)) == 2
