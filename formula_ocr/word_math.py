"""Equation-array alignment and explicit n-ary operands for Word's math importers."""
import xml.etree.ElementTree as ET


ML = '{http://www.w3.org/1998/Math/MathML}'
OM = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
ET.register_namespace('m', OM[1:-1])


def aligned_equations(math):
    """Identify the outer two-column layout whose alignment boundary is an equals sign."""
    table = math
    while table.tag in (ML + 'math', ML + 'mrow', ML + 'semantics'):
        if not len(table) or (table.tag != ML + 'semantics' and len(table) != 1):
            return None
        table = table[0]
    if table.tag != ML + 'mtable' or len(table) < 2:
        return None
    rows = []
    for row in table:
        if row.tag != ML + 'mtr' or len(row) != 2 or any(c.tag != ML + 'mtd' for c in row):
            return None
        left, right = row
        align = table.get('columnalign') or ' '.join(cell.get('columnalign', 'center') for cell in row)
        if align != 'right left':
            return None
        lhs = list(left)
        rhs = [n for n in right if n.tag != ML + 'mi' or n.text or len(n)]
        if not (rhs and rhs[0].tag == ML + 'mo' and rhs[0].text == '='):
            if not (lhs and lhs[-1].tag == ML + 'mo' and lhs[-1].text == '='):
                return None
            rhs.insert(0, lhs.pop())
        rows.append((lhs, rhs))
    return table, rows


_SCRIPTS = {ML + s for s in ('munder', 'mover', 'munderover', 'msub', 'msup', 'msubsup')}
_NARY = frozenset('∑∏∐∫∬∭∮∯∰⋀⋁⋂⋃⨀⨁⨂⨄⨆')
_OPEN = frozenset('([{⟨⌊⌈')
_CLOSE = frozenset(')]}⟩⌋⌉')
_BOUNDARIES = frozenset('+-−±∓=≠≈∼≃≡<>≤≥∈∉⊂⊃⊆⊇→←↔,;:.')
_ACCENTS = {'~': '\u0303', '^': '\u0302', '˙': '\u0307', '¨': '\u0308',
            '¯': '\u0305', '―': '\u0305', '→': '\u20d7', '←': '\u20d6',
            '↔': '\u20e1', 'ˇ': '\u030c', '˘': '\u0306', '´': '\u0301',
            '`': '\u0300', '˚': '\u030a'}
_GROUP_CHARS = frozenset('⏞⏟⏜⏝⎴⎵')
_LOWER_BARS = frozenset(('¯', '―', '\u0305', '\u0332'))
_LOWER_ARROWS = frozenset('←→↔')


def _operator(node):
    while node.tag in _SCRIPTS and len(node):
        node = node[0]
    return node.text if node.tag == ML + 'mo' else None


def _operand_end(nodes, start):
    depth = 0
    for i in range(start, len(nodes)):
        op = _operator(nodes[i])
        if op in _OPEN:
            depth += 1
        elif op in _CLOSE:
            if not depth:
                return i
            depth -= 1
        elif not depth and op in _BOUNDARIES:
            if i != start or op not in ('+', '-', '−', '±', '∓'):
                return i
    return len(nodes)


def _group_operands(math):
    # Office binds a sum/product/integral only to its immediately following mrow.
    # Work inside sibling sequences, never across fraction, script or matrix slots.
    sequences = {ML + s for s in ('math', 'mrow', 'mtd', 'mstyle', 'msqrt', 'mpadded')}
    for row in list(math.iter()):
        if row.tag not in sequences:
            continue
        nodes = list(row)
        for i in range(len(nodes) - 2, -1, -1):
            node = nodes[i]
            if node.tag not in _SCRIPTS or _operator(node) not in _NARY:
                continue
            end = _operand_end(nodes, i + 1)
            if end <= i + 1:
                continue
            operand = ET.Element(ML + 'mrow')
            operand.extend(nodes[i + 1:end])
            operation = ET.Element(ML + 'mrow')
            operation.extend((node, operand))
            nodes[i:end] = [operation]
        row[:] = nodes


def prepare_word_mathml(math, *, for_omml=False):
    for over in math.iter(ML + 'mover'):
        if (len(over) == 2 and over[1].tag == ML + 'mo' and over[1].text == '~'
                and over.get('accent') != 'false' and over[1].get('accent') != 'false'):
            # latex2mathml writes a spacing tilde; Office needs a combining accent.
            over.set('accent', 'true')
            over[1].text = '\u0303'
    _group_operands(math)
    aligned = aligned_equations(math)
    if aligned is None:
        return False
    table, rows = aligned
    table.attrib.pop('columnspacing', None)
    table.attrib.pop('columnalign', None)
    for row, (lhs, rhs) in zip(table, rows):
        cell = ET.Element(ML + 'mtd')
        row[:] = [cell]
        if not for_omml:
            ET.SubElement(cell, ML + 'maligngroup')
        cell.extend(lhs)
        if for_omml:
            # Native eqArr uses a literal ampersand run as its alignment marker.
            ET.SubElement(cell, ML + 'mo').text = '&'
        else:
            ET.SubElement(cell, ML + 'malignmark')
        cell.extend(rhs)
    return True


def _prepare_decorations(math):
    # mathml2omml emits a mismatched closing tag for stretchy accents. Route
    # these through its valid limit objects, then attach the decoration below.
    for node in list(math.iter()):
        if node.tag not in (ML + 'mover', ML + 'munder') or len(node) != 2:
            continue
        mark = node[1]
        if mark.tag != ML + 'mo':
            continue
        accent_attr = 'accent' if node.tag == ML + 'mover' else 'accentunder'
        if node.get(accent_attr) == 'false' or mark.get('accent') == 'false':
            # An explicit non-accent is an ordinary limit, even if its glyph is
            # normally an accent. A row also prevents accidental reconstruction.
            row = ET.Element(ML + 'mrow')
            row.append(mark)
            node[1] = row
            continue
        char = mark.text
        if node.tag == ML + 'mover':
            char = _ACCENTS.get(char, char)
            handled = char in _ACCENTS.values() or char in _GROUP_CHARS
        else:
            handled = char in _LOWER_BARS or char in _LOWER_ARROWS or char in _GROUP_CHARS
        if handled:
            mark.text = char
            mark.set('stretchy', 'false')


def _restore_decorations(wrapper):
    for node in list(wrapper.iter()):
        if node.tag not in (OM + 'limUpp', OM + 'limLow'):
            continue
        char = node.findtext(OM + 'lim/' + OM + 'r/' + OM + 't')
        position = 'top' if node.tag == OM + 'limUpp' else 'bot'
        if position == 'top' and char in _ACCENTS.values():
            kind = 'bar' if char == '\u0305' else 'acc'
        elif position == 'bot' and char in _LOWER_BARS:
            kind = 'bar'
        elif char in _GROUP_CHARS or (position == 'bot' and char in _LOWER_ARROWS):
            kind = 'groupChr'
        else:
            continue
        base = node.find(OM + 'e')
        node.clear()
        node.tag = OM + kind
        props = ET.SubElement(node, OM + kind + 'Pr')
        if kind != 'bar':
            ET.SubElement(props, OM + 'chr', {OM + 'val': char})
        if kind != 'acc':
            ET.SubElement(props, OM + 'pos', {OM + 'val': position})
        if kind == 'groupChr':
            # Keep the base on the baseline and the brace outside it. In
            # particular, an overbrace needs bot justification, not the default.
            ET.SubElement(props, OM + 'vertJc',
                          {OM + 'val': 'bot' if position == 'top' else 'top'})
        node.append(base)


def native_omml(math):
    import mathml2omml

    aligned = prepare_word_mathml(math, for_omml=True)
    _prepare_decorations(math)
    for fraction in math.iter(ML + 'mfrac'):
        # latex2mathml uses unitless zero for binomials. mathml2omml only
        # recognises zero followed by a unit when emitting a noBar fraction.
        if fraction.get('linethickness', '').strip() == '0':
            fraction.set('linethickness', '0pt')
    content = mathml2omml.convert(ET.tostring(math, encoding='unicode'))
    wrapper = ET.fromstring('<root xmlns:m="' + OM[1:-1] + '">' + content + '</root>')
    if aligned:
        matrix = wrapper.find('.//' + OM + 'm')
        matrix.tag = OM + 'eqArr'
        # Each converted cell wraps its runs in m:box/m:e. The ampersand
        # must be a direct run of eqArr/m:e or Word prints it as text.
        matrix[:] = [row.find(OM + 'e/' + OM + 'box/' + OM + 'e')
                     for row in matrix.findall(OM + 'mr')]
    for nary in wrapper.iter(OM + 'nary'):
        props = nary.find(OM + 'naryPr')
        for limit in ('sub', 'sup'):
            slot = nary.find(OM + limit)
            if slot is not None and not len(slot):
                ET.SubElement(props, OM + limit + 'Hide', {OM + 'val': '1'})
    _restore_decorations(wrapper)
    # DOCX and Office HTML provide different namespaces for these same m: tags.
    return ET.tostring(wrapper, encoding='unicode', short_empty_elements=True).split('>', 1)[1][:-len('</root>')]
