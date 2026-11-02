import xml.etree.ElementTree as ET
from unittest.mock import patch, Mock

import pytest
import requests
from formula_ocr.core import clean_latex, endpoint, export_text, mathml, recognize


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
