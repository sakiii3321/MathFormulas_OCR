"""Preserve equation alignment when desktop MathType imports Presentation MathML."""
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
        data = _relation_pile(_native_equation(left_xml), _native_equation(right_xml), rows)
        return _annotation(data) if data else None
    finally:
        if status >= 0:
            ole.CoUninitialize()


def add_mathtype_alignment(math):
    if sys.platform != 'win32':
        return
    lines = _equation_lines(math)
    if lines is None:
        return
    ns = math.tag.removesuffix('math')
    source = ET.Element(math.tag, math.attrib)
    source.append(lines)
    left_xml = ET.tostring(source, encoding='us-ascii', xml_declaration=False).decode('ascii')
    lines.set('columnalign', 'right')
    right_xml = ET.tostring(source, encoding='us-ascii', xml_declaration=False).decode('ascii')
    try:
        import pywintypes
    except ImportError:
        return
    try:
        annotation = _native_alignment(left_xml, right_xml, len(lines))
    except (pywintypes.com_error, pywintypes.error, ImportError):
        # MathType is optional. Word and other readers use Presentation MathML.
        return
    if annotation:
        presentation = math[0]
        math.remove(presentation)
        semantics = ET.SubElement(math, ns + 'semantics')
        semantics.append(presentation)
        ET.SubElement(semantics, ns + 'annotation', encoding='MathType-MTEF').text = annotation
