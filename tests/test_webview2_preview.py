from unittest.mock import patch

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

pytest.importorskip('sideview')
from sideview import NativeWebViewError
from formula_ocr.webview2_preview import RUNTIME_URL, WebView2Preview

APP = QApplication.instance() or QApplication([])


def test_unavailable_runtime_leaves_preview_help_and_other_actions_usable(tmp_path):
    with patch('formula_ocr.webview2_preview.DpiWebView', side_effect=NativeWebViewError('test <failure>')):
        view = WebView2Preview(profile_path=tmp_path)
    assert not view.message.isHidden()
    assert RUNTIME_URL in view.message.text()
    assert '识别、编辑、复制及导出仍可使用' in view.message.text()
    assert '&lt;failure&gt;' in view.message.text()
    view.setHtml('<p>Updating the editor remains possible without a browser.</p>')
    view.setUrl(QUrl.fromLocalFile(str(tmp_path / 'preview.html')))
    with pytest.raises(ValueError, match='本地'):
        view.setUrl(QUrl('https://example.com'))
    view.dispose()
    view.deleteLater()
