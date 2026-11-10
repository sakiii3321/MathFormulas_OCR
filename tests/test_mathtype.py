import ctypes
import os
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pytest

from formula_ocr.core import export_text, mathml
from formula_ocr.mathtype import _annotation, _equation_lines, _relation_pile
from formula_ocr.mixed import to_omml
from formula_ocr.word_math import OM


LOSSES = r"""\begin{aligned}
\mathcal{L} &= \mathcal{L}_{\text{T}} + \lambda \mathcal{L}_{\text{Lap}}, \\
\mathcal{L}_{\text{T}} &= \frac{1}{|\Omega|}\sum_{(i,j)\in\Omega}\tilde{e}_{i,j}^{2}, \\
\mathcal{L}_{\text{Lap}} &= \frac{1}{|\Omega_{\Delta}|s_{\text{Lap}}^{2}}
\sum_{(i,j)\in\Omega_{\Delta}}(\Delta_{xz}\tilde{e})_{i,j}^{2}.
\end{aligned}"""


def portable(latex):
    with patch('formula_ocr.core.add_mathtype_alignment'):
        return ET.fromstring(export_text(latex, 'MathML'))


@pytest.mark.parametrize('latex', [LOSSES, LOSSES.replace('&=', '=&'),
                                  LOSSES.replace('aligned', 'align*')])
def test_native_lines_keep_math_content_and_portable_columns(latex):
    root = portable(latex)
    lines = _equation_lines(root)
    assert [len(row) for row in root.findall('.//{*}mtr')] == [2, 2, 2]
    assert [len(row) for row in lines] == [1, 1, 1]
    assert ''.join(lines.itertext()) == ''.join(root.itertext())
    assert len(lines.findall('.//{*}mfrac')) == len(lines.findall('.//{*}munder')) == 2


@pytest.mark.parametrize('latex', [
    r'a=b', r'\begin{pmatrix}a&=b\\c&=d\end{pmatrix}',
    r'\begin{aligned}a&=b&&x\\b&=c&&y\end{aligned}',
    r'\begin{align}a&=b\\c&=d\end{align}',  # Numbered third column.
    r'u+\begin{aligned}a&=b\\c&=d\end{aligned}',
    r'\begin{aligned}a&b\\c&d\end{aligned}',
])
def test_other_layouts_do_not_request_native_conversion(latex):
    assert _equation_lines(portable(latex)) is None


def test_only_outer_native_record_changes():
    header = bytes((5, 0, 1, 0, 1, 3, 1, 0, 0))
    prefix, lines = b'\x05prefs', b'\x01nested' + header + b'\0\0'
    left = prefix + header + lines
    right = prefix + header[:3] + b'\x02' + header[4:] + lines
    assert _relation_pile(left, right, 3) == prefix + b'\x04\x00\x04\x01' + lines
    assert _relation_pile(left, right, 2) is None
    assert _relation_pile(left, right[:-1] + b'x', 3) is None
    assert _relation_pile(left, left, 3) is None
    assert _annotation(b'\x05\x01\x00') == 'MathType@MTEF@5@5@+=\n  feaa@0006@'


def test_missing_mathtype_preserves_export():
    pythoncom = pytest.importorskip('pythoncom')
    with patch('formula_ocr.mathtype._native_alignment',
               side_effect=pythoncom.com_error(-2147221164, 'Class not registered', None, None)):
        root = ET.fromstring(export_text(LOSSES, 'MathML'))
    assert root.find('.//{*}mtable').get('columnalign') == 'right left'
    assert root.find('.//{*}annotation') is None
    assert 'MathType-MTEF' not in mathml(LOSSES)


def native(latex):
    return ET.fromstring('<root xmlns:m="' + OM[1:-1] + '">' + to_omml(latex) + '</root>')


@pytest.mark.parametrize('latex', [LOSSES, LOSSES.replace('&=', '=&')])
def test_word_alignment_and_summands_without_mathtype(latex):
    with patch('formula_ocr.core.add_mathtype_alignment'):
        presentation = ET.fromstring(mathml(latex, for_word=True))
    for cell in presentation.findall('.//{*}mtd'):
        assert cell[0].tag.endswith('}maligngroup')
        mark = list(cell).index(cell.find('{*}malignmark'))
        assert cell[mark + 1].text == '='
    result = native(latex)
    lines = result.findall('.//{*}eqArr/{*}e')
    assert len(lines) == 3
    for line in lines:
        # A marker inside a grouping box prints a visible ampersand in Word.
        assert '&' in [r.text for r in line.findall('{*}r/{*}t')]
    expected = ['ei,j2', '(Δxze)i,j2']
    operands = [p[1] for p in presentation.iter() if len(p) == 2 and p[0].tag.endswith('}munder')]
    assert [''.join(e.itertext()).replace('\u0303', '') for e in operands] == expected
    assert len(result.findall('.//{*}acc/{*}accPr/{*}chr')) == 2
    sums = result.findall('.//{*}nary')
    assert [''.join(n.find('{*}e').itertext()) for n in sums] == expected
    assert all(n.find('{*}naryPr/{*}supHide').get(OM + 'val') == '1' for n in sums)


def test_nary_scope_and_limits_in_a_real_matrix():
    result = native(r'\begin{pmatrix}\sum_{i=1}^n (a_i+b_i)+c&d\\e&\prod_{j}x_j\end{pmatrix}')
    assert result.find('.//{*}m') is not None and result.find('.//{*}eqArr') is None
    total, product = result.findall('.//{*}nary')
    assert ''.join(total.find('{*}e').itertext()) == '(ai+bi)'
    assert total.find('{*}naryPr/{*}supHide') is None
    assert ''.join(total.find('{*}sup').itertext()) == 'n'
    assert ''.join(product.find('{*}e').itertext()) == 'xj'


def test_office_mathml_importer_builds_an_equation_array_with_full_summands():
    from lxml import etree
    paths = (Path(os.environ.get(key, '.')) / 'Microsoft Office/root/Office16/MML2OMML.XSL'
             for key in ('ProgramFiles', 'ProgramFiles(x86)'))
    stylesheet = next((p for p in paths if p.is_file()), None)
    if stylesheet is None:
        pytest.skip('requires the desktop Office MathML stylesheet')
    transform = etree.XSLT(etree.parse(str(stylesheet)))
    with patch('formula_ocr.mathtype._native_alignment', return_value='MathType test annotation'):
        source = mathml(LOSSES, for_word=True)
    result = transform(etree.fromstring(source.encode('ascii'))).getroot()
    rows = result.findall('.//{*}eqArr/{*}e')
    assert len(rows) == 3 and all('&' in [r.text for r in row.findall('{*}r/{*}t')] for row in rows)
    assert 'annotation' not in ''.join(result.itertext())
    operands = result.findall('.//{*}nary/{*}e')
    assert [''.join(op.itertext()) for op in operands] == ['ei,j2', '(Δxze)i,j2']


def _metafile(markup):
    import pythoncom
    import win32clipboard
    obj = pythoncom.CoCreateInstance('Equation.DSMT4', None, pythoncom.CLSCTX_LOCAL_SERVER,
                                     pythoncom.IID_IDataObject)
    fmt = win32clipboard.RegisterClipboardFormat('MathML')
    data = pythoncom.STGMEDIUM()
    data.set(pythoncom.TYMED_HGLOBAL, (markup + '\0').encode('utf-16-le'))
    obj.SetData((fmt, None, 1, -1, pythoncom.TYMED_HGLOBAL), data, False)
    picture = obj.GetData((3, None, 1, -1, pythoncom.TYMED_MFPICT))  # CF_METAFILEPICT

    class MetafilePicture(ctypes.Structure):
        _fields_ = [('mm', ctypes.c_long), ('xExt', ctypes.c_long), ('yExt', ctypes.c_long),
                    ('hMF', ctypes.c_void_p)]

    kernel = ctypes.windll.kernel32
    kernel.GlobalLock.argtypes = kernel.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel.GlobalLock.restype = ctypes.POINTER(MetafilePicture)
    pointer = kernel.GlobalLock(picture.data)
    assert pointer
    try:
        get_bits = ctypes.windll.gdi32.GetMetaFileBitsEx
        get_bits.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p]
        handle = pointer.contents.hMF
        size = get_bits(handle, 0, None)
        buffer = ctypes.create_string_buffer(size)
        assert size and get_bits(handle, size, buffer) == size
        return buffer.raw
    finally:
        kernel.GlobalUnlock(picture.data)


def _equals_origins(wmf):
    # MathType sets the current pen position before drawing a run of glyphs.
    pos, x, y = 18, 0, 0
    origins = []
    while pos < len(wmf):
        words, record = struct.unpack_from('<IH', wmf, pos)
        assert words >= 3
        if record == 0x0214:  # META_MOVETO
            y, x = struct.unpack_from('<hh', wmf, pos + 6)
        elif record == 0x0a32 and wmf[pos + 14:pos + 15] == b'=':  # META_EXTTEXTOUT
            origins.append((x, y))
        pos += words * 2
    return origins


@pytest.mark.skipif(os.getenv('TEST_DESKTOP_MATHTYPE') != '1', reason='requires desktop MathType')
def test_desktop_mathtype_draws_three_equals_at_one_x_coordinate():
    original = ET.tostring(portable(LOSSES), encoding='unicode')
    before = _equals_origins(_metafile(original))
    after = _equals_origins(_metafile(export_text(LOSSES, 'MathML')))
    assert _equals_origins(_metafile(mathml(LOSSES, for_word=True))) == after
    assert len(before) == len(after) == len({y for _, y in after}) == 3
    assert len({x for x, _ in before}) > 1
    assert len({x for x, _ in after}) == 1
