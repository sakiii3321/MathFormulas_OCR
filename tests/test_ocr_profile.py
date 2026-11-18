from unittest.mock import Mock, patch

import pytest

from formula_ocr.core import PROMPT, recognize
from formula_ocr.prompts import DEEPSEEK_FLASH_PROMPT


@pytest.mark.parametrize('base,model,specialized', [
    ('https://api.deepseek.com', 'deepseek-flash', True),
    ('https://api.deepseek.com/v1/', 'deepseek-v4.1-flash', True),
    ('https://api.deepseek.com', 'deepseek-v4-pro', False),
    ('https://api.openai.com/v1', 'vision', False),
    ('https://api.siliconflow.cn/v1', 'deepseek-flash', False),
    ('https://proxy.example/api.deepseek.com', 'deepseek-flash', False),
])
def test_only_official_flash_uses_the_validated_profile(base, model, specialized):
    response = Mock(status_code=200)
    response.json.return_value = {'choices': [{'message': {'content': r'\dot{x}+0.125x'}}]}
    with patch('formula_ocr.core.requests.post', return_value=response) as post:
        assert recognize(b'image', base, 'test-secret', model) == r'\dot{x}+0.125x'
    post.assert_called_once()
    prompt = post.call_args.kwargs['json']['messages'][0]['content']
    assert prompt == (DEEPSEEK_FLASH_PROMPT if specialized else PROMPT)
    assert 'test-secret' not in prompt
