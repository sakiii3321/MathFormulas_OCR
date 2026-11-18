"""Keep grouping marks and labels editable in native Office math."""
import os
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

import pytest

from formula_ocr.mixed import to_omml
from formula_ocr.word_math import ML, OM, native_omml


@pytest.fixture(autouse=True)
def no_desktop_conversion():
    # These tests exercise the portable OMML path, never MathType COM.
    with patch('formula_ocr.core.add_mathtype_alignment'):
        yield


def native(latex):
    return ET.fromstring(f'<root xmlns:m="{OM[1:-1]}">{to_omml(latex)}</root>')


def text(node):
    return ''.join(node.itertext())


@pytest.mark.parametrize('command,char,position,limit', [
    (r'\overbrace', '⏞', 'top', 'limUpp'),
    (r'\underbrace', '⏟', 'bot', 'limLow'),
])
@pytest.mark.parametrize('label', [False, True])
def test_grouping_braces_keep_base_and_optional_label(command, char, position, limit, label):
    latex = command + r'{x_1+\frac{y}{z}}'
    if label:
        latex += ('^' if position == 'top' else '_') + r'{n+1}'
    result = native(latex)
    group = result.find('.//' + OM + 'groupChr')
    assert group is not None
    assert [n.tag for n in group] == [OM + 'groupChrPr', OM + 'e']
    props = group.find(OM + 'groupChrPr')
    assert props.find(OM + 'chr').get(OM + 'val') == char
    assert props.find(OM + 'pos').get(OM + 'val') == position
    assert props.find(OM + 'vertJc').get(OM + 'val') == ('bot' if position == 'top' else 'top')
    assert text(group.find(OM + 'e')) == 'x1+yz'
    assert group.find('.//' + OM + 'f') is not None
    outer = result.find('.//' + OM + limit)
    if label:
        assert outer.find(OM + 'e/' + OM + 'groupChr') is group
        assert text(outer.find(OM + 'lim')) == 'n+1'
    else:
        assert outer is None


def test_m35_multinomial_with_two_labeled_overbraces():
    latex = (r'M_1=\binom{n}{\overbrace{1,\ldots,1}^{a_1},\ldots,'
             r'\overbrace{n,\ldots,n}^{a_n}}'
             r'=\frac{n!}{(1!)^{a_1}(2!)^{a_2}\cdots(n!)^{a_n}}.')
    result = native(latex)
    groups = result.findall('.//' + OM + 'groupChr')
    assert [text(n.find(OM + 'e')) for n in groups] == ['1,…,1', 'n,…,n']
    assert [text(n.find(OM + 'lim')) for n in result.findall('.//' + OM + 'limUpp')] == ['a1', 'an']
    binomial = result.find('.//' + OM + 'f')
    assert binomial.find(OM + 'fPr/' + OM + 'type').get(OM + 'val') == 'noBar'
    assert len(binomial.findall('.//' + OM + 'groupChr')) == 2
    assert len(result.findall('.//' + OM + 'f')) == 2


def test_nested_braces_keep_accent_and_both_labels_in_their_own_scope():
    result = native(r'\underbrace{\overbrace{\dot{x}+y}^{a}+z}_{b}')
    outer = result.find('.//' + OM + 'limLow')
    assert text(outer.find(OM + 'lim')) == 'b'
    lower_group = outer.find(OM + 'e/' + OM + 'groupChr')
    inner = lower_group.find('.//' + OM + 'limUpp')
    assert text(inner.find(OM + 'lim')) == 'a'
    upper_group = inner.find(OM + 'e/' + OM + 'groupChr')
    assert text(upper_group.find(OM + 'e')) == 'x+y'
    assert upper_group.find('.//' + OM + 'acc/' + OM + 'accPr/' + OM + 'chr').get(OM + 'val') == '\u0307'
    assert text(lower_group.find(OM + 'e')).endswith('+z')


def test_binomial_has_no_fraction_rule_but_an_ordinary_fraction_keeps_it():
    result = native(r'\binom{n}{k}+\frac{n}{k}')
    binomial, fraction = result.findall('.//' + OM + 'f')
    assert binomial.find(OM + 'fPr/' + OM + 'type').get(OM + 'val') == 'noBar'
    assert fraction.find(OM + 'fPr/' + OM + 'type') is None
    assert [text(n) for n in (binomial, fraction)] == ['nk', 'nk']


@pytest.mark.parametrize('command', [r'\underline', r'\underbar'])
def test_lower_bar_is_attached_and_extends_over_the_whole_base(command):
    result = native(command + r'{x+y}_{i}')
    bar = result.find('.//' + OM + 'bar')
    assert bar.find(OM + 'barPr/' + OM + 'pos').get(OM + 'val') == 'bot'
    assert text(bar.find(OM + 'e')) == 'x+y'
    assert text(result.find('.//' + OM + 'sSub/' + OM + 'sub')) == 'i'
    assert result.find('.//' + OM + 'limLow') is None


@pytest.mark.parametrize('command,char', [
    (r'\overleftarrow', '\u20d6'), (r'\overrightarrow', '\u20d7'),
    (r'\overleftrightarrow', '\u20e1'), (r'\check', '\u030c'),
    (r'\breve', '\u0306'), (r'\acute', '\u0301'),
    (r'\grave', '\u0300'), (r'\mathring', '\u030a'),
    (r'\widehat', '\u0302'), (r'\widetilde', '\u0303'),
])
def test_standard_accents_attach_without_becoming_limits(command, char):
    result = native(command + r'{xy}')
    accent = result.find('.//' + OM + 'acc')
    assert accent.find(OM + 'accPr/' + OM + 'chr').get(OM + 'val') == char
    assert text(accent.find(OM + 'e')) == 'xy'
    assert result.find('.//' + OM + 'limUpp') is None


@pytest.mark.parametrize('command,char', [
    (r'\underleftarrow', '←'), (r'\underrightarrow', '→'),
    (r'\underleftrightarrow', '↔'),
])
def test_lower_arrows_are_group_characters(command, char):
    result = native(command + r'{AB}')
    group = result.find('.//' + OM + 'groupChr')
    assert group.find(OM + 'groupChrPr/' + OM + 'chr').get(OM + 'val') == char
    assert group.find(OM + 'groupChrPr/' + OM + 'pos').get(OM + 'val') == 'bot'
    assert text(group.find(OM + 'e')) == 'AB'


def test_ordinary_overset_and_underset_remain_limits():
    result = native(r'\overset{n+1}{x}+\underset{k\to0}{y}+\overset{\rightarrow}{z}')
    uppers = result.findall('.//' + OM + 'limUpp')
    assert [text(n.find(OM + 'lim')) for n in uppers] == ['n+1', '→']
    assert text(result.find('.//' + OM + 'limLow/' + OM + 'lim')) == 'k→0'
    assert result.find('.//' + OM + 'acc') is None
    assert result.find('.//' + OM + 'groupChr') is None


@pytest.mark.parametrize('tag,attribute,char', [
    ('mover', 'accent', '\u0305'), ('mover', 'accent', '~'),
    ('mover', 'accent', '⏞'), ('munder', 'accentunder', '⏟'),
])
def test_explicit_non_accent_marks_are_not_reinterpreted(tag, attribute, char):
    source = ET.fromstring(f'<math xmlns="{ML[1:-1]}"><{tag} {attribute}="false">'
                           f'<mi>x</mi><mo stretchy="true">{char}</mo></{tag}></math>')
    result = ET.fromstring(f'<root xmlns:m="{OM[1:-1]}">{native_omml(source)}</root>')
    limit = result.find('.//' + OM + ('limUpp' if tag == 'mover' else 'limLow'))
    assert text(limit.find(OM + 'lim')) == char
    assert result.find('.//' + OM + 'groupChr') is None
    assert result.find('.//' + OM + 'bar') is None


def test_office_stylesheet_reads_group_characters_and_nested_labels():
    from lxml import etree
    paths = (Path(os.environ.get(key, '.')) / 'Microsoft Office/root/Office16/OMML2MML.XSL'
             for key in ('ProgramFiles', 'ProgramFiles(x86)'))
    stylesheet = next((p for p in paths if p.is_file()), None)
    if stylesheet is None:
        pytest.skip('requires the desktop Office OMML stylesheet')
    transform = etree.XSLT(etree.parse(str(stylesheet)))
    source = native(r'\overbrace{x+y}^{n}+\underbrace{a+b}_{k}')
    result = transform(etree.fromstring(ET.tostring(source.find(OM + 'oMath')))).getroot()
    overs = result.findall('.//' + ML + 'mover')
    unders = result.findall('.//' + ML + 'munder')
    assert any(text(n[0]) == 'x+y' and text(n[1]) == '⏞' for n in overs)
    assert any(text(n[0]) == 'a+b' and text(n[1]) == '⏟' for n in unders)
    assert 'n' in text(result) and 'k' in text(result)
