import xml.etree.ElementTree as ET
from unittest.mock import patch, Mock

import pytest
import requests
from formula_ocr.core import clean_latex, endpoint, export_text, mathml, recognize


BOUNDARY_CONDITIONS = r"""\begin{aligned}
\mathbf{u} &= \mathbf{u}_D &&\text{on } \Gamma_D^F \\
\left[\eta\left(\nabla \mathbf{u} + \nabla \mathbf{u}^T\right) - pI\right]\cdot \mathbf{n} &= \mathbf{g}_N &&\text{on } \Gamma_N^F \\
T &= T_D &&\text{on } \Gamma_D^T \\
k\nabla T \cdot \mathbf{n} &= q_N &&\text{on } \Gamma_N^T
\end{aligned}"""
MATH_NS = {'m': 'http://www.w3.org/1998/Math/MathML'}


@pytest.mark.parametrize('environment', ['aligned', 'align*'])
def test_alignment_and_spacing_work_in_mathml_core(environment):
    latex = BOUNDARY_CONDITIONS.replace('aligned', environment)
    table = ET.fromstring(mathml('$$' + latex + '$$')).find('.//m:mtable', MATH_NS)
    rows = table.findall('m:mtr', MATH_NS)
    assert len(rows) == 4
    for row in rows:
        cells = row.findall('m:mtd', MATH_NS)
        assert len(cells) == 4
        for index, cell in enumerate(cells):
            alignment = 'right' if index % 2 == 0 else 'left'
            assert cell.get('columnalign') == alignment
            assert f'text-align:{alignment}' in cell.get('style', '')
            assert f'text-align:-webkit-{alignment}' in cell.get('style', '')
            assert 'padding-left:0' in cell.get('style', '')
        assert 'padding-right:0em' in cells[0].get('style', '')
        assert 'padding-right:2em' in cells[1].get('style', '')


def test_nested_matrix_keeps_its_centered_columns():
    root = ET.fromstring(mathml(r'\begin{aligned}x&=\begin{pmatrix}a&bb\\ccc&d\end{pmatrix}\\y&=2\end{aligned}'))
    outer, matrix = root.findall('.//m:mtable', MATH_NS)
    assert 'text-align:right' in outer.find('m:mtr/m:mtd', MATH_NS).get('style', '')
    assert all(cell.get('style') is None for cell in matrix.findall('m:mtr/m:mtd', MATH_NS))


def test_array_alignment_and_escaped_ampersand_are_preserved():
    root = ET.fromstring(mathml(r'\begin{array}{rl}a&b\\long&A\&B\end{array}'))
    cells = root.findall('.//m:mtd', MATH_NS)
    assert len(cells) == 4
    assert 'text-align:right' in cells[0].get('style', '')
    assert 'text-align:left' in cells[1].get('style', '')
    assert '&' in ''.join(root.itertext())


def test_mathtype_export_preserves_bold_vectors_without_supplementary_characters():
    markup = export_text(BOUNDARY_CONDITIONS, 'MathML')
    assert markup.isascii()
    tree = ET.fromstring(markup)
    text = ''.join(tree.itertext())
    assert all(ord(char) <= 0xffff for char in text)
    bold = tree.findall('.//m:mi[@mathvariant="bold"]', MATH_NS)
    assert {node.text for node in bold} == {'u', 'g', 'n'}
    assert len(bold) == 7
    assert '\u0393' in text and '\u03b7' in text and '\u2207' in text
    assert '\u00a0' not in text
    assert len(tree.findall('.//m:mspace[@width="0.25em"]', MATH_NS)) == 4
    assert all('style' not in node.attrib for node in tree.iter())
    assert len(tree.findall('.//m:mtr', MATH_NS)) == 4
    table = tree.find('.//m:mtable', MATH_NS)
    assert table.get('columnalign') == 'right left left'
    assert table.get('columnspacing') == '0em 2em'
    assert all(len(row) == 3 for row in table.findall('m:mtr', MATH_NS))
    assert tree.find('.//m:mtd', MATH_NS).get('columnalign') == 'right'
    preview = mathml(BOUNDARY_CONDITIONS)
    assert chr(0x1d42e) in preview
    assert 'text-align:-webkit-right' in preview


@pytest.mark.parametrize('latex,letter,variant', [
    (r'\mathbb{R}', 'R', 'double-struck'), (r'\mathcal{L}', 'L', 'script'),
    (r'\mathfrak{g}', 'g', 'fraktur'), (r'\mathit{h}', 'h', 'italic'),
    (r'\mathbf{\alpha}', '\u03b1', 'bold'), (r'\mathsf{A}', 'A', 'sans-serif'),
])
def test_mathtype_math_variants(latex, letter, variant):
    tree = ET.fromstring(export_text(latex, 'MathML'))
    assert any(node.text == letter and node.get('mathvariant') == variant for node in tree.iter())


@pytest.mark.parametrize('latex,expected', [
    (r'\boldsymbol{n}', '\U0001d48f'),
    (r'\boldsymbol{\alpha}', '\U0001d736'),
    (r'\boldsymbol{\Gamma}', '\U0001d71e'),
    (r'\boldsymbol{\nabla}', '\U0001d6c1'),
    (r'\boldsymbol{x_1}', '\U0001d499\U0001d7cf'),
])
def test_boldsymbol_preview_uses_actual_bold_math_glyphs(latex, expected):
    root = ET.fromstring(mathml(latex))
    assert ''.join(root.itertext()) == expected
    exported = ET.fromstring(export_text(latex, 'MathML'))
    assert all(ord(char) <= 0xffff for char in ''.join(exported.itertext()))
    assert any('bold' in node.get('mathvariant', '') for node in exported.iter())


def test_boldsymbol_preserves_operators_and_regular_letters():
    root = ET.fromstring(mathml(r'n + \boldsymbol{n+u}'))
    assert ''.join(root.itertext()) == 'n+\U0001d48f+\U0001d496'
    operators = root.findall('.//m:mo', MATH_NS)
    assert operators[0].get('style') is None
    assert 'font-weight:bold' in operators[1].get('style', '')


@pytest.mark.parametrize('value', [r'\[x^2\]', '$$x^2$$', '```latex\nx^2\n```', '$x^2$'])
def test_delimiters(value):
    assert clean_latex(value) == 'x^2'


def test_formats_and_mathml():
    assert export_text('x^2', '$ … $') == '$x^2$'
    assert export_text('x', 'equation') == '\\begin{equation}\nx\n\\end{equation}'
    tree = ET.fromstring(mathml(r'\frac{a}{b}+\sqrt{x}'))
    ns = {'m': 'http://www.w3.org/1998/Math/MathML'}
    assert tree.find('.//m:mfrac', ns) is not None
    assert tree.find('.//m:msqrt', ns) is not None


@pytest.mark.parametrize('latex', [r'\begin{pmatrix}a&b\\c&d\end{pmatrix}', r'\sum_{i=1}^{n}x_i', r'\begin{aligned}a&=b\\c&=d\end{aligned}'])
def test_complex_math(latex):
    ET.fromstring(mathml(latex))


def test_endpoint():
    assert endpoint('https://example.com/v1/') == 'https://example.com/v1/chat/completions'
    assert endpoint('http://localhost:8000/v1/chat/completions') == 'http://localhost:8000/v1/chat/completions'
    with pytest.raises(ValueError):
        endpoint('http://remote.example/v1')


def test_request_and_response():
    response = Mock(status_code=200)
    response.json.return_value = {'choices': [{'message': {'content': '$x$'}, 'finish_reason': 'stop'}]}
    with patch('formula_ocr.core.requests.post', return_value=response) as post:
        assert recognize(b'PNG', 'https://example.com/v1', 'secret', 'vision') == 'x'
        args = post.call_args.kwargs
        assert args['json']['messages'][1]['content'][0]['image_url']['url'] == 'data:image/png;base64,UE5H'
        assert args['headers']['Authorization'] == 'Bearer secret'
        assert args['allow_redirects'] is False


@pytest.mark.parametrize('status', [401, 403, 404, 429, 500])
def test_api_errors(status):
    with patch('formula_ocr.core.requests.post', return_value=Mock(status_code=status)):
        with pytest.raises(ValueError, match=str(status)):
            recognize(b'p', 'https://example.com/v1', 'key', 'vision')


def test_timeout():
    with patch('formula_ocr.core.requests.post', side_effect=requests.Timeout):
        with pytest.raises(ValueError, match='超时'):
            recognize(b'p', 'https://example.com/v1', '', 'vision')


def test_truncation_and_empty():
    response = Mock(status_code=200)
    response.json.return_value = {'choices': [{'message': {'content': 'x'}, 'finish_reason': 'length'}]}
    with patch('formula_ocr.core.requests.post', return_value=response):
        with pytest.raises(ValueError, match='截断'):
            recognize(b'p', 'https://example.com/v1', '', 'vision')
    with pytest.raises(ValueError):
        clean_latex('NO_FORMULA')


@pytest.mark.parametrize('name,expected', [
    ('OpenAI 官方', 'https://api.openai.com/v1/chat/completions'),
    ('硅基流动', 'https://api.siliconflow.cn/v1/chat/completions'),
    ('DeepSeek 官方', 'https://api.deepseek.com/chat/completions'),
])
def test_provider_requests(name, expected):
    from formula_ocr.providers import PROVIDERS
    response = Mock(status_code=200)
    response.json.return_value = {'choices': [{'message': {'content': 'x'}}]}
    with patch('formula_ocr.core.requests.post', return_value=response) as post:
        recognize(b'p', PROVIDERS[name][0], 'provider-key', 'vision-model')
        assert post.call_args.args[0] == expected
