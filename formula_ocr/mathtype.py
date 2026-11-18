"""Optional native MathType compatibility, with unchanged Presentation MathML."""
import copy
import ctypes
import string
import sys
import xml.etree.ElementTree as ET
from functools import lru_cache

from .word_math import aligned_equations


def _equation_lines(math):
    """Join the two alignment columns into complete lines for a MathType pile."""
    ns = math.tag.removesuffix('math')
    aligned = aligned_equations(math)
    if aligned is None or len(aligned[1]) > 255:
        return None
    lines = ET.Element(ns + 'mtable', columnalign='left')
    for left, right in aligned[1]:
        line = ET.SubElement(ET.SubElement(lines, ns + 'mtr'), ns + 'mtd')
        line.extend(left)
        line.extend(right)
    return lines


def _native_equation(xml):
    import pythoncom
    import win32clipboard
    from win32com import storagecon

    # Use a new in-memory OLE object. No Word window, file or clipboard write.
    # Registered CLSID of the desktop MathType equation (Equation.DSMT4).
    obj = pythoncom.CoCreateInstance('{0002CE03-0000-0000-C000-000000000046}', None,
                                     pythoncom.CLSCTX_LOCAL_SERVER,
                                     pythoncom.IID_IDataObject)
    mode = storagecon.STGM_SHARE_EXCLUSIVE | storagecon.STGM_READWRITE | storagecon.STGM_CREATE
    storage = pythoncom.StgCreateDocfileOnILockBytes(pythoncom.CreateILockBytesOnHGlobal(), mode, 0)
    persist = obj.QueryInterface(pythoncom.IID_IPersistStorage)
    persist.InitNew(storage)
    medium = pythoncom.STGMEDIUM()
    medium.set(pythoncom.TYMED_HGLOBAL, (xml + '\0').encode('utf-16-le'))
    fmt = (win32clipboard.RegisterClipboardFormat('MathML'), None, pythoncom.DVASPECT_CONTENT,
           -1, pythoncom.TYMED_HGLOBAL)
    obj.SetData(fmt, medium, False)
    persist.Save(storage, True)
    stream = storage.OpenStream('Equation Native', None, storagecon.STGM_SHARE_EXCLUSIVE, 0)
    stream_size = stream.Seek(0, 2)
    stream.Seek(0, 0)
    header = stream.Read(28)  # EQNOLEFILEHDR.cbHdr and .cbObject
    size = int.from_bytes(header[8:12], 'little')
    if len(header) != 28 or int.from_bytes(header[:2], 'little') != 28 or size > stream_size - 28:
        return b''
    return stream.Read(size)


def _relation_pile(left, right, rows):
    # The two native equations differ only in the alignment byte of the outer
    # MATRIX. This identifies it even with custom font definitions or nested
    # matrices, without decoding or guessing offsets inside the equation body.
    if not left.startswith(b'\x05') or len(left) != len(right):
        return None
    index = next((i for i, (a, b) in enumerate(zip(left, right)) if a != b), None)
    if index is None or index < 3 or left[index + 1:] != right[index + 1:]:
        return None
    start = index - 3
    partition_bytes = (rows + 4) // 4 + 1  # Two bits per row/column boundary.
    header = bytes((5, 0, 1, 0, 1, rows, 1)) + bytes(partition_bytes)
    if right[index] != 2 or not left.startswith(header + b'\x01', start):
        return None
    # Both records own the same list of LINEs. PILE halign=4 anchors each
    # complete line at its relation, so resizing either side keeps it aligned.
    return left[:start] + bytes((4, 0, 4, 1)) + left[start + len(header):]


def _annotation(data):
    # MathType's text interchange uses least-significant sextets first.
    alphabet = string.ascii_letters + string.digits + '+='
    chars = []
    for pos in range(0, len(data), 3):
        chunk = data[pos:pos + 3]
        value = int.from_bytes(chunk, 'little')
        chars.extend(alphabet[(value >> shift) & 63] for shift in range(0, 8 * len(chunk), 6))
    encoded = ''.join(chars)
    body = '\n  '.join(encoded[pos:pos + 56] for pos in range(0, len(encoded), 56))
    return f'MathType@MTEF@5@5@+=\n  {body}@{sum(data) & 0xffff:04X}@'


def _compatible_source(math):
    """Build a private import copy for the legacy desktop MathML translator.

    These substitutions must never reach the portable presentation tree: Word
    and browsers support the original Unicode characters directly.
    """
    source = copy.deepcopy(math)
    ns = math.tag.removesuffix('math')
    changed = False
    aliases = {'\u00b7': '\u22c5', '\u27e8': '\u2329', '\u27e9': '\u232a'}
    for node in list(source.iter()):
        if node.tag not in (ns + 'mi', ns + 'mo') or len(node):
            continue
        if not node.text and node.tag == ns + 'mo' and node.get('fence') == 'true':
            # A null delimiter crashes MathType's fence importer. Keep an
            # empty group so fixed-arity parents retain their argument slots.
            node.tag, node.attrib = ns + 'mrow', {}
        elif (node.text in ('\u2016', '\u2225') and node.get('fence') == 'true'
              and node.get('stretchy') == 'true'):
            # MathType's legacy translator has no double-bar fence template;
            # its stretchy path rejects the whole equation (FORMATETC).
            # Retain both norm characters as fixed-size glyphs in native data.
            node.set('stretchy', 'false')
        elif node.text in aliases:
            node.tag, node.text = ns + 'mo', aliases[node.text]
        elif node.text == '\u2020':
            # Times New Roman ANSI runs such as "0\x86" render as "0?" in
            # Word on a Chinese Windows codepage. Explicit Cambria isolates
            # the dagger in a supported font. mathvariant overrides fontfamily
            # in MathType's importer, so retain bold through fontweight instead.
            variant = node.attrib.pop('mathvariant', '')
            if 'bold' in variant:
                node.set('fontweight', 'bold')
            node.tag = ns + 'mo'
            node.set('fontfamily', 'Cambria Math')
            node.set('fontstyle', 'normal')
        elif node.text in ('\u2aaf', '\u2ab0'):
            # The old MTCode table lacks these straight-line relations. A
            # native underbar embellishment keeps that shape; U+227C/U+227D
            # would incorrectly substitute the curved-line variants.
            base = '\u227a' if node.text == '\u2aaf' else '\u227b'
            attributes = dict(node.attrib)
            node.tag, node.text, node.attrib = ns + 'munder', None, {'accentunder': 'true'}
            ET.SubElement(node, ns + 'mo', attributes).text = base
            ET.SubElement(node, ns + 'mo').text = '\u00af'
        else:
            continue
        changed = True
    return source, changed


@lru_cache(maxsize=8)
def _native_alignment(left_xml, right_xml, rows):
    import pythoncom
    # Balance our own COM reference. pythoncom's main-thread initialization is
    # shared with Qt/OLE and must survive copying an equation.
    ole = ctypes.windll.ole32
    status = ole.CoInitializeEx(None, pythoncom.COINIT_APARTMENTTHREADED)
    if status < 0 and status != -2147417850:  # RPC_E_CHANGED_MODE: already initialized.
        return None
    try:
        data = (_relation_pile(_native_equation(left_xml), _native_equation(right_xml), rows)
                if right_xml is not None else _native_equation(left_xml))
        return _annotation(data) if data else None
    finally:
        if status >= 0:
            ole.CoUninitialize()


def add_mathtype_alignment(math):
    if sys.platform != 'win32':
        return
    source, changed = _compatible_source(math)
    lines = _equation_lines(source)
    if lines is None and not changed:
        return
    ns = math.tag.removesuffix('math')
    if lines is not None:
        source = ET.Element(math.tag, math.attrib)
        source.append(lines)
    left_xml = ET.tostring(source, encoding='us-ascii', xml_declaration=False).decode('ascii')
    right_xml = None
    if lines is not None:
        lines.set('columnalign', 'right')
        right_xml = ET.tostring(source, encoding='us-ascii', xml_declaration=False).decode('ascii')
    try:
        import pywintypes
    except ImportError:
        return
    try:
        annotation = _native_alignment(left_xml, right_xml, len(lines) if lines is not None else 0)
    except (pywintypes.com_error, pywintypes.error, ImportError):
        # MathType is optional. Word and other readers use Presentation MathML.
        return
    if annotation:
        presentation = math[0]
        math.remove(presentation)
        semantics = ET.SubElement(math, ns + 'semantics')
        semantics.append(presentation)
        ET.SubElement(semantics, ns + 'annotation', encoding='MathType-MTEF').text = annotation
