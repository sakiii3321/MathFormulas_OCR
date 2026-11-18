r"""Small structural adapters for latex2mathml 3.81.1.

The upstream tokenizer erases the font of compact ``\mathrm{x}``, and its
converter emits matrix fences beside (rather than around) the matrix argument.
Row-break optional lengths are also not consumed by the upstream matrix parser.
Keep these adaptations at token/AST boundaries; never remove bracketed formula
text by searching the resulting XML.
"""

from decimal import Decimal
import re
from xml.etree.ElementTree import SubElement

from latex2mathml import commands
from latex2mathml.converter import Converter
from latex2mathml.tokenizer import PATTERN


_FENCED_MATRICES = frozenset(
    (r"\pmatrix", r"\bmatrix", r"\Bmatrix", r"\vmatrix", r"\Vmatrix")
)
_LENGTH = re.compile(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))(pt|pc|in|cm|mm|em|ex|bp|dd|cc|sp|mu)?")
_POINTS = {
    "pt": Decimal(1), "pc": Decimal(12), "in": Decimal("72.27"),
    "cm": Decimal("72.27") / Decimal("2.54"),
    "mm": Decimal("72.27") / Decimal("25.4"),
    "bp": Decimal("72.27") / Decimal(72),
    "dd": Decimal(1238) / Decimal(1157),
    "cc": Decimal(12 * 1238) / Decimal(1157),
    "sp": Decimal(1) / Decimal(65536),
}


def _number(value):
    return format(value.normalize(), "f") if value else "0"


def _dimension(text):
    match = _LENGTH.fullmatch(text)
    if not match:
        return None
    value = Decimal(match[1])
    unit = match[2]
    if unit is None:
        return (value, "pt") if value == 0 else None
    if unit == "mu":
        return value / Decimal(18), "em"
    if unit in ("bp", "dd", "cc", "sp"):
        return value * _POINTS[unit], "pt"
    return value, unit


def _length_text(dimension):
    value, unit = dimension
    return _number(value) + unit


def _portable_gap(base, extra):
    """MathML 3 length; its space-separated list cannot contain CSS calc().

For a mixed font-relative/absolute sum, use the explicit positive length (or a
zero gap for negative adjustments). This is a portable spacing approximation;
the preview CSS retains the actual sum. Formula content is never changed.
"""
    base_value, base_unit = base
    extra_value, extra_unit = extra
    if not extra_value:
        return _length_text(base)
    if base_unit == extra_unit:
        return _length_text((max(Decimal(0), base_value + extra_value), base_unit))
    if base_unit in _POINTS and extra_unit in _POINTS:
        total = base_value * _POINTS[base_unit] + extra_value * _POINTS[extra_unit]
        return _length_text((max(Decimal(0), total), "pt"))
    return _length_text(extra) if extra_value > 0 else "0pt"


def _preview_gap(base, extra):
    value, unit = extra
    if not value:
        return _length_text(base)
    sign = "+" if value > 0 else "-"
    return f"max(0px, calc({_length_text(base)} {sign} {_number(abs(value))}{unit}))"


def _font_safe_source(latex):
    # Use the library's lexer, so comments, escaped backslashes and text/verb
    # arguments are not mistaken for font commands in mathematical content.
    pieces, offset = [], 0
    for token in PATTERN.finditer(latex):
        if token.group("math_font") != commands.MATHRM:
            continue
        position = token.start("math_arg")
        pieces.extend((latex[offset:position], " "))
        offset = position
    pieces.append(latex[offset:])
    return "".join(pieces)


def _row_breaks(nodes):
    """Consume a concrete optional length only immediately after an AST \\ node."""
    nodes = list(nodes)
    output, lengths = [], {}
    index = row = 0
    while index < len(nodes):
        node = nodes[index]
        output.append(node)
        index += 1
        if node.token not in (commands.DOUBLEBACKSLASH, commands.CARRIAGERETURN):
            continue
        previous_row = row
        row += 1
        if node.token != commands.DOUBLEBACKSLASH:
            continue
        # Star only inhibits a TeX page break; it has no meaning in one MathML table.
        if index < len(nodes) and nodes[index].token == "*" and nodes[index].children is None:
            index += 1
        if index >= len(nodes) or nodes[index].token != "[":
            continue
        end = index + 1
        while end < len(nodes) and nodes[end].children is None and nodes[end].token != "]":
            if nodes[end].token in ("[", "&", commands.DOUBLEBACKSLASH, commands.CARRIAGERETURN):
                break
            end += 1
        if end >= len(nodes) or nodes[end].token != "]":
            continue
        dimension = _dimension("".join(part.token for part in nodes[index + 1:end]))
        if dimension is not None:
            lengths[previous_row] = dimension
            index = end + 1
    return output, lengths


class _NormalizedConverter(Converter):
    def __init__(self, display, for_preview):
        super().__init__(display=display)
        self.for_preview = for_preview

    def _convert_command(self, node, parent, font=None):
        command = node.token.rstrip("*")
        if command in _FENCED_MATRICES:
            # A scripted matrix is ONE operand, including both fences. Grouping
            # here also keeps adjacent matrices and nested fences independent.
            parent = SubElement(parent, "mrow")
            # Upstream parses starred alignment but omits its matrix delimiters.
            node = node._replace(token=command)
        super()._convert_command(node, parent, font)

    def _convert_matrix(self, nodes, parent, command, alignment=None):
        nodes, lengths = _row_breaks(nodes)
        super()._convert_matrix(iter(nodes), parent, command, alignment)
        if not lengths:
            return
        rows = parent.findall("mtr")
        base_lengths = parent.get("rowspacing", "1ex").split()
        portable = []
        for index in range(max(0, len(rows) - 1)):
            base = _dimension(base_lengths[min(index, len(base_lengths) - 1)])
            extra = lengths.get(index, (Decimal(0), "pt"))
            portable.append(_portable_gap(base, extra))
            if self.for_preview:
                for cell in rows[index].findall("mtd"):
                    cell.set("style", "padding-top:0;padding-bottom:" + _preview_gap(base, extra))
        if portable:
            parent.set("rowspacing", " ".join(portable))
        if self.for_preview and rows:
            for cell in rows[-1].findall("mtd"):
                cell.set("style", "padding-top:0;padding-bottom:0")


def convert_mathml(latex: str, display: str = "inline", *, for_preview: bool = False) -> str:
    """Convert cleaned LaTeX; replace ``latex2mathml.converter.convert`` in core.

    Core should keep its existing ``aligned`` to ``align*`` adaptation, call this
    before its XML/variant/export processing, and append its column CSS to any
    existing mtd style. ``for_preview=False`` produces portable MathML without CSS.
    Raw source/exported LaTeX is never rewritten.
    """
    return _NormalizedConverter(display, for_preview).convert(_font_safe_source(latex))
