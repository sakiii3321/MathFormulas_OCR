"""Real WebView2 preview/Word export smoke test; OCR is mocked and clipboard restored."""
import json
import random
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QBuffer, QIODevice, QMimeData, QSettings, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication
from formula_ocr.app import Window
from formula_ocr.mixed import MIXED_EXAMPLE, MIXED_WORD, from_markdown, save_document
from formula_ocr.theme import theme_colors
from formula_ocr.webview2_preview import WebView2Preview

app = QApplication([])
app.setStyle('Fusion')
app.setQuitOnLastWindowClosed(False)
root = Path(tempfile.mkdtemp(prefix='webview2-smoke-', dir='.tmp')).resolve()
backup = QMimeData()
original = app.clipboard().mimeData()
for fmt in original.formats():
    backup.setData(fmt, original.data(fmt))
settings = QSettings(str(root / 'settings.ini'), QSettings.Format.IniFormat)
settings.setValue('capture/hotkey', 'Ctrl+Alt+Shift+F10')
settings.setValue('base', 'http://localhost:12345/v1')
settings.setValue('model', 'mock-vision')
settings.setValue('mixed_copy/enabled', True)
settings.setValue('mixed_copy/format', MIXED_WORD)
with patch('formula_ocr.app.create_preview', side_effect=lambda backend: WebView2Preview(profile_path=root / 'profile')):
    window = Window(settings, preview_backend='webview2')
window.show()
window.editor.setPlainText(r'\frac{a}{b}')
phase = 'formula'
finished = False
doc = from_markdown(MIXED_EXAMPLE)
mock = patch('formula_ocr.app.recognize_mixed', return_value=doc)
recognize = mock.start()


def finish(code):
    global finished
    if finished:
        return
    finished = True
    poll.stop()
    if window.worker and window.worker.isRunning():
        window.worker.wait()
    window.quit_application()
    mock.stop()
    app.clipboard().setMimeData(backup)
    app.exit(code)


def inspect(data):
    global phase
    if finished:
        return
    try:
        if phase == 'formula' and data['math'] == 1:
            assert data['fractionHeight'] > 20, data
            assert abs(data['width'] - window.preview._view.width()) <= 2, data
            print('PASS: native MathML fraction, widget sizing; DPR=' + str(data['dpr']), flush=True)
            window.mode.setCurrentIndex(1)
            window.png = b'mock source; no network request'
            window.start_recognition()
            phase = 'mixed'
        elif phase == 'mixed' and data['math'] == 17:
            assert 'Bayesian regularization' in data['text']
            assert '(4)' in data['text'] and '(6)' in data['text']
            assert 'Bayesian regularization' in app.clipboard().mimeData().html()
            assert recognize.call_count == 1
            path = root / 'mixed.docx'
            save_document(window.mixed_document(), path, 'DOCX')
            with ZipFile(path) as z:
                tree = ET.fromstring(z.read('word/document.xml'))
                ns = {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math',
                      'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                assert len(tree.findall('.//m:oMath', ns)) == 17
                assert len(tree.findall('.//w:tabs', ns)) == 3
                assert tree.find('.//w:tbl', ns) is None
            window.night_switch.setChecked(True)
            phase = 'night'
        elif phase == 'night':
            color = QColor(theme_colors(True)['sheet'])
            expected = f'rgb({color.red()}, {color.green()}, {color.blue()})'
            if data['background'] != expected:
                return
            print('PASS: mixed prose, 17 equations, Word clipboard, DOCX tab stops and dark preview.', flush=True)
            pixels = random.Random(0).randbytes(800 * 600 * 3)
            image = QImage(pixels, 800, 600, QImage.Format.Format_RGB888).copy()
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            assert image.save(buffer, 'PNG')
            doc.assets['figure-1.png'] = bytes(buffer.data())
            doc.blocks.append({'type': 'image', 'asset': 'figure-1.png'})
            window.got_result(doc)
            phase = 'large'
        elif phase == 'large' and data['href'].startswith('file:') and data['images'] == 1 and data['imagesLoaded']:
            assert data['math'] == 17
            window.resize(1000, 700)
            window.close()
            assert not window.isVisible()
            window.show_main_window()
            phase = 'restored'
        elif phase == 'restored':
            assert window.isVisible()
            assert data['math'] == 17 and data['imagesLoaded']
            assert abs(data['width'] - window.preview._view.width()) <= 2, data
            phase = 'capture'
            window.preview._view.capture_frame()
        elif phase == 'csp' and 'CSP check' in data['text']:
            assert not data['pageScriptRan']
            print('PASS: large local-file preview, embedded PNG, resizing/tray restore and page CSP.', flush=True)
            assert not any(name.startswith('PySide6.QtWebEngine') for name in sys.modules)
            print('PASS: WebView2 session uses no Qt WebEngine modules.', flush=True)
            finish(0)
    except Exception:
        import traceback
        traceback.print_exc()
        finish(1)


def check():
    if not window.preview._view._native_ready:
        return
    window.preview.runJavaScript("""({text:document.body?.innerText || '',
        math:document.querySelectorAll('math').length,
        fractionHeight:document.querySelector('mfrac')?.getBoundingClientRect().height || 0,
        background:document.body ? getComputedStyle(document.body).backgroundColor : '',
        images:document.images.length, imagesLoaded:[...document.images].every(i=>i.complete && i.naturalWidth>0),
        width:innerWidth, dpr:devicePixelRatio, href:location.href, pageScriptRan:!!window.pageScriptRan})""", inspect)


def captured(_request, data):
    global phase
    path = root / 'preview.png'
    path.write_bytes(data)
    print('PREVIEW_IMAGE=' + str(path), flush=True)
    # Page content cannot run scripts; host ExecuteScript remains available for inspection.
    window.preview.setHtml('<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src \'none\'"><body>CSP check<script>window.pageScriptRan=true</script></body>')
    phase = 'csp'


window.preview._view.captureCompleted.connect(captured)
poll = QTimer()
poll.setInterval(400)
poll.timeout.connect(check)
poll.start()
QTimer.singleShot(30000, lambda: finish(2))
code = app.exec()
# Leave this ignored test profile for debugging; the runtime releases its files asynchronously.
sys.exit(code)
