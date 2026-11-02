"""Exercise mixed OCR UI with a mock model response and real HTML/clipboard."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QMimeData, QSettings, QTimer
from PySide6.QtWidgets import QApplication
from formula_ocr.app import Window, STYLE
from formula_ocr.mixed import MIXED_EXAMPLE, MIXED_WORD, from_markdown, to_markdown

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
backup = QMimeData()
old = app.clipboard().mimeData()
for fmt in old.formats():
    backup.setData(fmt, old.data(fmt))
temp = tempfile.TemporaryDirectory(dir='.tmp')
settings = QSettings(str(Path(temp.name) / 'mixed.ini'), QSettings.Format.IniFormat)
settings.setValue('capture/hotkey', 'Ctrl+Alt+Shift+F10')
settings.setValue('base', 'http://localhost:12345/v1')
settings.setValue('model', 'mock-vision')
settings.setValue('mixed_copy/enabled', True)
settings.setValue('mixed_copy/format', MIXED_WORD)
window = Window(settings)
window.resize(1250, 950)
window.show()
window.editor.setPlainText('x^2')
window.mode.setCurrentIndex(1)
doc = from_markdown(MIXED_EXAMPLE)
mock = patch('formula_ocr.app.recognize_mixed', return_value=doc)
mock.start()
finished = False


def finish(code):
    global finished
    if finished:
        return
    finished = True
    mock.stop()
    window.close()
    app.clipboard().setMimeData(backup)
    app.exit(code)


def inspect(text):
    try:
        assert 'Bayesian regularization' in text and '(4)' in text and '(6)' in text
        assert 'Bayesian regularization' in app.clipboard().mimeData().html()
        assert not app.clipboard().mimeData().hasFormat('application/mathml+xml')
        assert window.editor.toPlainText() == to_markdown(doc)
        Path('artifacts').mkdir(exist_ok=True)
        window.grab().save('artifacts/mixed-preview.png')
        window.mode.setCurrentIndex(0)
        assert window.editor.toPlainText() == 'x^2'
        window.mode.setCurrentIndex(1)
        assert 'Bayesian regularization' in window.editor.toPlainText()
        print('PASS: mixed worker, editor, rendered prose/math/numbers, Word clipboard and preserved formula draft.', flush=True)
        finish(0)
    except Exception:
        import traceback
        traceback.print_exc()
        finish(1)


def start():
    window.png = b'mock image; no network request'
    window.start_recognition()
    QTimer.singleShot(5000, lambda: window.preview.page().toPlainText(inspect))


QTimer.singleShot(800, start)
QTimer.singleShot(20000, lambda: finish(2))
sys.exit(app.exec())
