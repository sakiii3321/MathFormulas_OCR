import json
from unittest.mock import Mock, patch
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from formula_ocr.clipboard import copy_mixed
from formula_ocr.mixed import (MIXED_EXAMPLE, MIXED_PROMPT, MIXED_WORD, MixedDocument,
    export_docx, export_mixed_text, from_markdown, parse_response, recognize_mixed,
    save_document, to_html, to_latex, to_markdown)
from test_capture_and_copy import APP, window, isolated_clipboard


def sample_response():
    return {'blocks': [
        {'type': 'paragraph', 'spans': [{'type': 'text', 'text': 'Weights '},
            {'type': 'math', 'latex': 'W'}, {'type': 'text', 'text': ' use Bayes’ theorem. 正文 $5 <tag> & #.'}]},
        {'type': 'equation', 'latex': r'\frac{a}{b}', 'number': '(4)'},
        {'type': 'paragraph', 'spans': [{'type': 'text', 'text': 'In Equations (5) and (6).'}]},
    ]}


def png_bytes():
    image = QImage(200, 100, QImage.Format.Format_RGB32)
    image.fill(0xffff0000)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    return bytes(buffer.data())


def test_api_structure_and_formula_prompt_is_not_reused():
    response = Mock(status_code=200)
    response.json.return_value = {'choices': [{'message': {'content': json.dumps(sample_response())}}]}
    with patch('formula_ocr.core.requests.post', return_value=response) as post:
        doc = recognize_mixed(png_bytes(), 'https://example.com/v1', 'key', 'vision')
    assert doc.blocks[1]['number'] == '4'
    assert post.call_args.kwargs['json']['messages'][0]['content'] == MIXED_PROMPT
    assert 'response_format' not in post.call_args.kwargs['json']  # Cross-provider compatibility.


def test_text_and_number_roundtrip_and_inline_math():
    doc = parse_response(json.dumps(sample_response()), png_bytes())
    edited = from_markdown(to_markdown(doc))
    assert edited.blocks == doc.blocks
    markup = to_html(edited)
    assert 'display="inline"' in markup and 'display="block"' in markup
    assert '(4)' in markup and '(5) and (6)' in markup
    assert '&lt;tag&gt; &amp; #' in markup
    assert '<a ' not in markup
    latex = to_latex(doc)
    assert '\\tag{4}' in latex and r'\$5' in latex


@pytest.mark.parametrize('content', ['```json\n{}\n```', 'not json', '{"blocks":[]}',
    '{"blocks":[{"type":"unknown"}]}', '{"blocks":[{"type":"paragraph","spans":[]}]}'])
def test_malformed_response_fails_without_partial_output(content):
    with pytest.raises(ValueError):
        parse_response(content, png_bytes())


def test_embedded_figure_is_exact_crop_and_exports_with_assets(tmp_path):
    data = sample_response()
    data['blocks'].insert(1, {'type': 'image', 'bbox': [100, 200, 600, 700]})
    doc = parse_response(json.dumps(data), png_bytes())
    image = QImage.fromData(doc.assets['figure-1.png'])
    assert (image.width(), image.height()) == (100, 50)
    assert image.pixelColor(0, 0).name() == '#ff0000'
    assert from_markdown(to_markdown(doc), doc.assets).blocks == doc.blocks
    assert 'data:image/png;base64,' in to_html(doc)
    assert 'data:image/png;base64,' in export_mixed_text(doc, 'Markdown')
    with pytest.raises(ValueError, match='插图'):
        export_mixed_text(doc, 'LaTeX')
    save_document(doc, tmp_path / 'mixed.md', 'Markdown')
    assert (tmp_path / 'mixed_assets/figure-1.png').read_bytes() == doc.assets['figure-1.png']
    assert '![](mixed_assets/figure-1.png)' in (tmp_path / 'mixed.md').read_text(encoding='utf-8')


@pytest.mark.parametrize('box', [[-1, 0, 500, 500], [0, 0, 1001, 1000], [500, 0, 0, 500], [0, 0, 'x', 1]])
def test_invalid_figure_bounds(box):
    with pytest.raises(ValueError):
        parse_response(json.dumps({'blocks': [{'type': 'image', 'bbox': box}]}), png_bytes())


@pytest.mark.parametrize('text', ['unfinished $x', '$$\nx^2', '![](asset:missing.png)', '![](file:///secret.png)'])
def test_editor_rejects_unfinished_math_or_unknown_images(text):
    with pytest.raises(ValueError):
        from_markdown(text)


def test_word_clipboard_keeps_whole_document_without_math_only_payload():
    doc = from_markdown(MIXED_EXAMPLE)
    copy_mixed(doc, MIXED_WORD)
    mime = APP.clipboard().mimeData()
    assert 'Bayesian regularization' in mime.html()
    assert '(4)' in mime.html() and '(5)' in mime.html() and '(6)' in mime.html()
    assert mime.hasHtml() and mime.hasText()
    assert not mime.hasFormat('application/mathml+xml')
    assert not any('x-qt-windows-mime' in name for name in mime.formats())
    assert 'msEquation 12' in mime.html()
    assert 'office/2004/12/omml' in mime.html()
    assert '<i>' in mime.html()
    special = to_html(from_markdown(r'The domain is $\mathbb{R}$.'), word=True)
    assert 'ℝ' in special
    assert '<m:rPr>' in special


def test_docx_native_equations_text_numbering_and_image(tmp_path):
    doc = from_markdown(MIXED_EXAMPLE)
    doc.blocks.append({'type': 'equation', 'latex': 'x^2', 'number': None})
    doc.assets['figure-1.png'] = png_bytes()
    doc.blocks.append({'type': 'image', 'asset': 'figure-1.png'})
    path = tmp_path / 'mixed.docx'
    export_docx(doc, path)
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
              'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
        text = ''.join(root.itertext())
        assert 'Bayesian regularization' in text
        assert '(4)' in text and '(5)' in text and '(6)' in text
        assert len(root.findall('.//m:oMath', ns)) > 10
        assert root.findall('.//m:f', ns)
        assert root.find('.//w:tbl', ns) is None
        numbered = [
            p for p in root.findall('.//w:p', ns) if p.find('w:pPr/w:tabs', ns) is not None]
        assert len(numbered) == 3
        for p, number in zip(numbered, ['(4)', '(5)', '(6)']):
            stops = p.findall('w:pPr/w:tabs/w:tab', ns)
            assert [s.get('{%s}val' % ns['w']) for s in stops] == ['center', 'right']
            assert len(p.findall('w:r/w:tab', ns)) == 2
            assert p.find('m:oMath', ns) is not None
            assert p.findall('w:r/w:t', ns)[-1].text == number
        assert len(root.findall('.//m:oMathPara', ns)) == 1
        assert len([p for p in archive.namelist() if p.startswith('word/media/')]) == 1
        assert '\\frac' not in text


def test_mode_switch_preserves_drafts_and_resets_for_new_image(window):
    window.editor.setPlainText('x^2')
    window.mode.setCurrentIndex(1)
    assert window.active_mode == 'mixed'
    assert window.editor.toPlainText() == ''
    window.editor.setPlainText('Original prose with $W$.')
    window.mode.setCurrentIndex(0)
    assert window.editor.toPlainText() == 'x^2'
    window.mode.setCurrentIndex(1)
    assert window.editor.toPlainText() == 'Original prose with $W$.'
    window.load_image(QImage.fromData(png_bytes()))
    window.mode.setCurrentIndex(0)
    assert window.editor.toPlainText() == ''
    assert not window.mixed_assets


def test_night_switch_updates_only_the_display(window):
    from PySide6.QtCore import QSettings
    from formula_ocr.theme import preview_css

    window.load_image(QImage.fromData(png_bytes()))
    original_png = window.png
    window.editor.setPlainText('x^2')
    window.mode.setCurrentIndex(1)
    window.show_example()
    export_before = export_mixed_text(window.mixed_document(), 'HTML')
    window.night_switch.click()
    saved = QSettings(window.settings.fileName(), QSettings.Format.IniFormat)
    assert saved.value('appearance/night', type=bool)
    assert preview_css(True) in window.preview.html
    assert window.editor.toPlainText() == MIXED_EXAMPLE and window.png == original_png
    assert export_mixed_text(window.mixed_document(), 'HTML') == export_before

    window.editor.setPlainText('unfinished $x')
    window.render()
    assert 'class="formula-error"' in window.preview.html and preview_css(True) in window.preview.html
    window.mode.setCurrentIndex(0)
    assert window.editor.toPlainText() == 'x^2'
    assert '<math' in window.preview.html and preview_css(True) in window.preview.html
    window.night_switch.click()
    assert preview_css(False) in window.preview.html
    assert not saved.value('appearance/night', type=bool)


def test_mixed_auto_copy_is_independent_of_formula_preferences(window):
    window.settings.setValue('copy/enabled', True)
    window.settings.setValue('copy/format', 'equation')
    window.mode.setCurrentIndex(1)
    APP.clipboard().setText('keep')
    doc = parse_response(json.dumps(sample_response()), png_bytes())
    window.got_result(doc)
    assert APP.clipboard().text() == 'keep'
    window.settings.setValue('mixed_copy/enabled', True)
    window.settings.setValue('mixed_copy/format', MIXED_WORD)
    window.got_result(doc)
    assert 'Weights' in APP.clipboard().mimeData().html()
    assert '已自动复制' in window.status.text()
    window.set_busy(True)
    assert not window.mode.isEnabled()
    window.set_busy(False)
    assert window.mode.isEnabled()
