"""Launch the real window, exercise editor/clipboard and save a preview screenshot."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from formula_ocr.app import Window, STYLE, EXAMPLE

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
window = Window()
window.show()
window.editor.setPlainText(EXAMPLE)
window.preview.loadFinished.connect(lambda ok: print('Preview loaded:', ok, flush=True))
window.preview.page().renderProcessTerminated.connect(lambda status, code: print('Renderer terminated:', status, code, flush=True))


def check():
    try:
        window.copy_word()
        mime = app.clipboard().mimeData()
        assert '<math' in mime.html()
        assert mime.hasFormat('application/mathml+xml')
        assert '已复制' in window.status.text()
        window.copy_code()
        assert app.clipboard().text() == EXAMPLE
        window.preview.page().toPlainText(check_preview)
        Path('artifacts').mkdir(exist_ok=True)
        assert window.grab().save('artifacts/app-preview.png')
        print('Window, conversion, clipboard and screenshot checks passed; checking preview…', flush=True)
    except Exception:
        import traceback
        traceback.print_exc()
        app.exit(1)


def check_preview(text):
    print('Preview text:', ascii(text), flush=True)
    if '100' in text:
        print('GUI smoke passed, including rendered formula content', flush=True)
    app.exit(0 if '100' in text else 1)


QTimer.singleShot(10000, check)
QTimer.singleShot(20000, lambda: app.exit(2))
sys.exit(app.exec())
