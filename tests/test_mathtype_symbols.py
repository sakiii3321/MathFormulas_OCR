"""Compatibility changes belong only in the optional native annotation."""
import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest

from formula_ocr.mathtype import _compatible_source, add_mathtype_alignment

NS = '{http://www.w3.org/1998/Math/MathML}'

def tree(body):
    return ET.fromstring('<math xmlns="'+NS[1:-1]+'"><mrow>'+body+'</mrow></math>')

@pytest.mark.parametrize('symbol,expected', [('·','⋅'),('⟨','〈'),('⟩','〉')])
def test_legacy_aliases_are_native_only(symbol,expected):
    original=tree('<mi>'+symbol+'</mi>');before=ET.tostring(original)
    source,changed=_compatible_source(original)
    assert changed and source[0][0].tag==NS+'mo'
    assert source[0][0].text==expected
    assert ET.tostring(original)==before


def test_dagger_font_is_not_overridden_by_mathvariant():
    original=tree('<msup><mi>a</mi><mrow><mn>0</mn><mo mathvariant="bold">†</mo></mrow></msup>')
    source,changed=_compatible_source(original)
    dagger=source.find('.//'+NS+'mo')
    assert changed and dagger.text=='†'
    assert dagger.attrib=={'fontfamily':'Cambria Math','fontstyle':'normal','fontweight':'bold'}
    assert original.find('.//'+NS+'mo').attrib=={'mathvariant':'bold'}


@pytest.mark.parametrize('symbol,base', [('⪯','≺'),('⪰','≻')])
def test_straight_line_relations_keep_their_shape(symbol,base):
    original=tree('<mo>'+symbol+'</mo>');source,changed=_compatible_source(original)
    relation=source[0][0]
    assert changed and relation.tag==NS+'munder'
    assert [child.text for child in relation]==[base,'¯']
    assert original[0][0].text==symbol


def test_invisible_delimiter_keeps_fixed_arity_argument():
    original=tree('<msub><mo fence="true"/><mn>0</mn></msub>')
    source,changed=_compatible_source(original)
    assert changed and len(source[0][0])==2
    assert source[0][0][0].tag==NS+'mrow'
    assert original[0][0][0].tag==NS+'mo'


@pytest.mark.parametrize('symbol', ['\u2016', '\u2225'])
def test_stretchy_norm_bar_is_disabled_only_for_native_import(symbol):
    original=tree('<mo fence="true" stretchy="true">'+symbol+'</mo><mi>g</mi><mo fence="true" stretchy="true">'+symbol+'</mo>')
    before=ET.tostring(original)
    source,changed=_compatible_source(original)
    assert changed and ET.tostring(original)==before
    bars=source.findall('.//'+NS+'mo')
    assert len(bars)==2 and all(n.text==symbol and n.get('stretchy')=='false' for n in bars)


def test_already_fixed_norm_bar_does_not_request_native_conversion():
    original=tree('<mo fence="false" stretchy="false">\u2016</mo>')
    source,changed=_compatible_source(original)
    assert not changed and ET.tostring(source)==ET.tostring(original)


@pytest.mark.parametrize('attributes', ['', ' fence="false"', ' stretchy="true"', ' fence="false" stretchy="true"'])
def test_parallel_relation_is_not_rewritten_as_a_norm(attributes):
    original=tree('<mi>a</mi><mo'+attributes+'>\u2225</mo><mi>b</mi>')
    source,changed=_compatible_source(original)
    assert not changed and ET.tostring(source)==ET.tostring(original)


@pytest.mark.parametrize('body', [
    '<mfrac><mi>a</mi><mi>b</mi></mfrac>',
    '<mtable><mtr><mtd><mi>a</mi></mtd><mtd><mi>b</mi></mtd></mtr><mtr><mtd><mi>c</mi></mtd><mtd><mi>d</mi></mtd></mtr></mtable>',
])
def test_tall_norm_keeps_content_and_portable_stretching(body):
    original=tree('<mo fence="true" stretchy="true">\u2016</mo>'+body+'<mo fence="true" stretchy="true">\u2016</mo>')
    before=ET.tostring(original)
    source,changed=_compatible_source(original)
    assert changed and ET.tostring(original)==before
    assert ET.tostring(source[0][1])==ET.tostring(original[0][1])
    assert all(n.get('stretchy')=='false' for n in source.findall('.//'+NS+'mo'))


@pytest.mark.parametrize('body', ['<mi>x</mi><mo>+</mo><mn>1</mn>', '<mtext>a·b†</mtext>', '<mo/>', '<mo>≽</mo>'])
def test_ordinary_content_needs_no_native_work(body):
    original=tree(body);source,changed=_compatible_source(original)
    assert not changed and ET.tostring(source)==ET.tostring(original)
    with patch('formula_ocr.mathtype._native_alignment') as native:
        add_mathtype_alignment(original)
    native.assert_not_called()


def test_annotation_preserves_portable_relation_and_null_delimiter():
    original=tree('<mo>⪰</mo><mo fence="true"/><mo>†</mo>')
    presentation=ET.tostring(original[0])
    with patch('formula_ocr.mathtype.sys.platform','win32'), patch('formula_ocr.mathtype._native_alignment',return_value='native-data') as native:
        pytest.importorskip('pywintypes')
        add_mathtype_alignment(original)
    assert ET.tostring(original[0][0])==presentation
    assert original.find('.//'+NS+'annotation').text=='native-data'
    imported=ET.fromstring(native.call_args.args[0])
    assert imported.find('.//'+NS+'munder') is not None
    assert native.call_args.args[1:]==(None,0)


def test_missing_mathtype_returns_unchanged_standard_mathml():
    pywintypes=pytest.importorskip('pywintypes')
    original=tree('<mo>⪰</mo><mo>†</mo>');before=ET.tostring(original)
    with patch('formula_ocr.mathtype.sys.platform','win32'), patch('formula_ocr.mathtype._native_alignment',side_effect=pywintypes.com_error(-2147221164,'not installed',None,None)):
        add_mathtype_alignment(original)
    assert ET.tostring(original)==before
