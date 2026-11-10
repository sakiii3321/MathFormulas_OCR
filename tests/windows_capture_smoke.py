"""Interactive Windows integration check using only a synthetic formula and mock OCR."""
import ctypes
import os
from ctypes import wintypes
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QMimeData, QPoint, QSettings, QTimer, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QSystemTrayIcon

from formula_ocr.app import PreferencesDialog, Window, STYLE

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
app.setQuitOnLastWindowClosed(False)
backup = QMimeData()
original = app.clipboard().mimeData()
for fmt in original.formats():
    backup.setData(fmt, original.data(fmt))

temp = tempfile.TemporaryDirectory(dir='.tmp')
settings = QSettings(str(Path(temp.name) / 'smoke.ini'), QSettings.Format.IniFormat)
settings.setValue('capture/hotkey', 'Ctrl+Alt+Shift+F10')
settings.setValue('window/ask_on_close', False)
settings.setValue('model', 'mock-vision')
settings.setValue('base', 'http://localhost:12345/v1')
settings.setValue('copy/enabled', True)
settings.setValue('copy/format', '$ … $')
mock_ocr = patch('formula_ocr.app.recognize', return_value='E=mc^2')
recognize = mock_ocr.start()
backend = 'webview2' if '--webview2' in sys.argv else 'qt'
if backend == 'webview2':
    os.environ['WEBVIEW2_USER_DATA_FOLDER'] = str(Path('.tmp/capture-webview2-profile').resolve())
window = Window(settings, preview_backend=backend)
window.show_on_startup(background=True)
assert not window.isVisible(), 'Background startup unexpectedly showed the main window'
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
phase = 'cancel_escape'
finished = False
preferences_checked = False


def finish(code):
    global finished
    if finished:
        return
    finished = True
    if window.capturing:
        window.capture.cancel()
    window.quit_application()
    marker.close()
    app.clipboard().setMimeData(backup)
    mock_ocr.stop()
    app.exit(code)


def send_hotkey():
    try:
        assert QSystemTrayIcon.isSystemTrayAvailable(), 'Windows system tray is unavailable'
        assert window.tray.isVisible(), 'Tray icon is not registered'
        window.close()
        assert not window.isVisible() and not window.closing, 'Close did not hide to tray'
        assert window.hotkey.id is not None, 'Native shortcut registration failed'
        # Deliver an actual Windows hotkey message without synthesizing user keystrokes.
        assert user32.PostThreadMessageW(thread_id, 0x0312, window.hotkey.id, 0)
        QTimer.singleShot(500, step)
    except Exception:
        import traceback
        traceback.print_exc()
        finish(1)


def check_preferences():
    global preferences_checked
    try:
        dialog = app.activeModalWidget()
        assert isinstance(dialog, PreferencesDialog), 'Tray settings did not open the preferences dialog'
        assert window.isVisible(), 'Tray settings did not restore the main window'
        assert dialog.close_action.currentData() == 'tray'
        assert dialog.autostart.isEnabled()
        assert dialog.grab().save(str(Path('.tmp') / f'preferences-{backend}.png'))
        preferences_checked = True
        dialog.reject()
    except Exception:
        import traceback
        traceback.print_exc()
        finish(1)


def step():
    global phase
    try:
        if phase in ('select', 'cancel_escape', 'cancel_right', 'exit_capture'):
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
            elif phase == 'exit_capture':
                window.tray_exit_action.trigger()
                assert window.closing and window.hotkey.id is None
                assert not window.capturing and not window.capture.overlays
                assert not window.isVisible()
                assert recognize.call_count == 1
                print('PASS: silent tray startup, close to tray, background hotkey, Escape/right-click stay hidden, screenshot restores window, mock OCR/auto-copy, tray restore and exit during capture.', flush=True)
                finish(0)
            else:
                old_png = window.png
                old_text = window.editor.toPlainText()
                old_clipboard = app.clipboard().text()
                if phase == 'cancel_escape':
                    QTest.keyClick(overlay, Qt.Key.Key_Escape)
                else:
                    QTest.mouseClick(overlay, Qt.MouseButton.RightButton)
                assert not window.capturing
                assert not window.isVisible(), 'Cancelled background capture showed the window'
                assert window.png == old_png
                assert window.editor.toPlainText() == old_text
                assert app.clipboard().text() == old_clipboard
                assert recognize.call_count == 0
                phase = 'cancel_right' if phase == 'cancel_escape' else 'select'
                send_hotkey()
        elif phase == 'recognized':
            assert window.worker and not window.worker.isRunning()
            assert window.isVisible() and not window.isMinimized(), 'Successful capture did not restore window'
            assert app.clipboard().text() == '$E=mc^2$'
            assert window.editor.toPlainText() == 'E=mc^2'
            captured = QImage.fromData(window.png)
            assert not captured.isNull()
            assert captured.pixelColor(4, 4).name() == '#ffffff'
            assert recognize.call_count == 1
            # The only image passed to mock OCR is the cropped synthetic formula.
            assert recognize.call_args.args[0] == window.png
            window.close()
            assert not window.isVisible()
            window.tray_menu.actions()[0].trigger()
            assert window.isVisible()
            window.close()
            QTimer.singleShot(150, check_preferences)
            next(action for action in window.tray_menu.actions() if action.text() == '使用设置').trigger()
            assert preferences_checked, 'Tray settings check did not complete'
            phase = 'exit_capture'
            send_hotkey()
    except Exception:
        import traceback
        traceback.print_exc()
        finish(1)


QTimer.singleShot(1000, send_hotkey)
QTimer.singleShot(20000, lambda: finish(2))
exit_code = app.exec()
if exit_code == 0:
    # Qt asks visible windows to close during quit; they must accept the final exit.
    window.show()
    QTimer.singleShot(100, window.quit_application)
    QTimer.singleShot(3000, lambda: app.exit(3))
    exit_code = app.exec()
    if exit_code == 0:
        print('PASS: explicit exit also terminates with the main window visible.', flush=True)
temp.cleanup()
sys.exit(exit_code)
