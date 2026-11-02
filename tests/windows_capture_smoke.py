"""Interactive Windows integration check using only a synthetic formula and mock OCR."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QMimeData, QPoint, QSettings, QTimer, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from formula_ocr.app import Window, STYLE, PreferencesDialog

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
backup = QMimeData()
original = app.clipboard().mimeData()
for fmt in original.formats():
    backup.setData(fmt, original.data(fmt))

temp = tempfile.TemporaryDirectory(dir='.tmp')
settings = QSettings(str(Path(temp.name) / 'smoke.ini'), QSettings.Format.IniFormat)
settings.setValue('capture/hotkey', 'Ctrl+Alt+Shift+F10')
settings.setValue('model', 'mock-vision')
settings.setValue('base', 'http://localhost:12345/v1')
settings.setValue('copy/enabled', True)
settings.setValue('copy/format', '$ … $')
mock_ocr = patch('formula_ocr.app.recognize', return_value='E=mc^2')
recognize = mock_ocr.start()
window = Window(settings)
window.show()
marker = QLabel('E = mc²', None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
marker.setStyleSheet('background: white; color: black; font-size: 48px;')
screen = app.primaryScreen()
center = screen.geometry().center()
marker.setGeometry(center.x() - 220, center.y() - 100, 440, 200)
marker.show()

user32 = ctypes.WinDLL('user32', use_last_error=True)
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
kernel32 = ctypes.WinDLL('kernel32')
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
thread_id = kernel32.GetCurrentThreadId()
phase = 'select'
finished = False


def finish(code):
    global finished
    if finished:
        return
    finished = True
    if window.capturing:
        window.capture.cancel()
    window.close()
    marker.close()
    app.clipboard().setMimeData(backup)
    mock_ocr.stop()
    app.exit(code)


def send_hotkey():
    try:
        assert window.hotkey.id is not None, 'Native shortcut registration failed'
        # Deliver an actual Windows hotkey message without synthesizing user keystrokes.
        assert user32.PostThreadMessageW(thread_id, 0x0312, window.hotkey.id, 0)
        QTimer.singleShot(500, step)
    except Exception:
        import traceback
        traceback.print_exc()
        finish(1)


def step():
    global phase
    try:
        if phase in ('select', 'cancel'):
            assert window.capturing and window.capture.overlays, 'Hotkey did not open capture overlay'
            overlay = next(item for item in window.capture.overlays if item.geometry().contains(center))
            if phase == 'select':
                start = overlay.mapFromGlobal(marker.geometry().topLeft() + QPoint(20, 20))
                end = overlay.mapFromGlobal(marker.geometry().bottomRight() - QPoint(20, 20))
                QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=start)
                QTest.mouseMove(overlay, end)
                QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=end)
                marker.hide()
                phase = 'recognized'
                QTimer.singleShot(700, step)
            else:
                old_png = window.png
                QTest.keyClick(overlay, Qt.Key.Key_Escape)
                assert not window.capturing
                assert window.png == old_png
                assert window.editor.toPlainText() == 'E=mc^2'
                assert app.clipboard().text() == '$E=mc^2$'
                assert recognize.call_count == 1
                dialog = PreferencesDialog(window)
                dialog.show()
                app.processEvents()
                Path('artifacts').mkdir(exist_ok=True)
                dialog.grab().save('artifacts/preferences-preview.png')
                dialog.close()
                print('PASS: native hotkey message, screen crop, mock OCR, automatic copy, Escape cancellation.', flush=True)
                finish(0)
        elif phase == 'recognized':
            assert window.worker and not window.worker.isRunning()
            assert app.clipboard().text() == '$E=mc^2$'
            assert window.editor.toPlainText() == 'E=mc^2'
            captured = QImage.fromData(window.png)
            assert not captured.isNull()
            assert captured.pixelColor(4, 4).name() == '#ffffff'
            assert recognize.call_count == 1
            # The only image passed to mock OCR is the cropped synthetic formula.
            assert recognize.call_args.args[0] == window.png
            phase = 'cancel'
            send_hotkey()
    except Exception:
        import traceback
        traceback.print_exc()
        finish(1)


QTimer.singleShot(1000, send_hotkey)
QTimer.singleShot(20000, lambda: finish(2))
exit_code = app.exec()
temp.cleanup()
sys.exit(exit_code)
