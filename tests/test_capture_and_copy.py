import ctypes
from ctypes import wintypes
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QMimeData, QPoint, QRectF, QSizeF, QSettings, Qt
from PySide6.QtGui import QImage, QKeySequence, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from formula_ocr.app import PreferencesDialog, Window
from formula_ocr.capture import SelectionOverlay, crop_selection
from formula_ocr.clipboard import CODE_FORMATS, WORD_FORMAT
from formula_ocr.core import export_text
from formula_ocr.hotkey import GlobalHotkey, parse_hotkey

APP = QApplication.instance() or QApplication([])


class MemoryClipboard:
    def __init__(self):
        self.mime = QMimeData()

    def setText(self, text):
        self.mime = QMimeData()
        self.mime.setText(text)

    def text(self):
        return self.mime.text()

    def mimeData(self):
        return self.mime

    def setMimeData(self, mime):
        self.mime = mime


@pytest.fixture(autouse=True)
def isolated_clipboard():
    # Unit tests must not depend on or replace the user's system clipboard.
    with patch.object(QApplication, 'clipboard', return_value=MemoryClipboard()):
        yield


@pytest.mark.parametrize('text,modifiers,vk', [('Ctrl+Shift+A', 6, 65), ('Alt+9', 1, 57), ('Ctrl+Alt+F8', 3, 0x77)])
def test_hotkey_mapping(text, modifiers, vk):
    assert parse_hotkey(text)[1:] == (modifiers, vk)


@pytest.mark.parametrize('text', ['', 'A', 'Shift+A', 'Ctrl+A, Ctrl+B', 'Ctrl+F12', 'Meta+A', 'Ctrl+Space'])
def test_reject_unsupported_hotkey(text):
    with pytest.raises(ValueError):
        parse_hotkey(text)


def test_hotkey_conflict_keeps_old_registration_and_routes_messages():
    api = Mock()
    api.RegisterHotKey.side_effect = [True, False, True]
    callback = Mock()
    hotkey = GlobalHotkey(callback, api)
    try:
        hotkey.register('Ctrl+Shift+A')
        old_id = hotkey.id
        with pytest.raises(ValueError):
            hotkey.register('Ctrl+Alt+B')
        assert hotkey.id == old_id
        api.UnregisterHotKey.assert_not_called()
        msg = wintypes.MSG()
        msg.message, msg.wParam = 0x0312, old_id
        assert hotkey.nativeEventFilter(b'windows_dispatcher_MSG', ctypes.addressof(msg)) == (True, 0)
        APP.processEvents()
        callback.assert_called_once()
        hotkey.register('Ctrl+Alt+B')
        api.UnregisterHotKey.assert_called_once_with(None, old_id)
        assert hotkey.nativeEventFilter(b'windows_dispatcher_MSG', ctypes.addressof(msg)) == (False, 0)
    finally:
        hotkey.close()


@pytest.mark.parametrize('scale', [1, 1.25, 1.5, 2])
def test_crop_dpi_reverse_drag_and_clipping(scale):
    source = QImage(int(200 * scale), int(100 * scale), QImage.Format.Format_RGB32)
    source.fill(Qt.GlobalColor.white)
    # Reverse-direction drag, in logical pixels.
    result = crop_selection(source, QRectF(100, 80, -80, -60), QSizeF(200, 100))
    assert result.width() == int(80 * scale)
    assert result.height() == int(60 * scale)
    assert result.devicePixelRatio() == 1
    clipped = crop_selection(source, QRectF(-30, -20, 50, 40), QSizeF(200, 100))
    assert clipped.width() == int(20 * scale)
    assert crop_selection(source, QRectF(1, 1, 2, 2), QSizeF(200, 100)).isNull()


def test_overlay_selection_and_escape():
    pixmap = QPixmap(200, 100)
    pixmap.fill(Qt.GlobalColor.white)
    overlay = SelectionOverlay(APP.primaryScreen(), pixmap)
    overlay.resize(200, 100)
    selected, cancelled = [], []
    overlay.selected.connect(selected.append)
    overlay.cancelled.connect(lambda: cancelled.append(True))
    QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    QTest.mouseMove(overlay, QPoint(100, 80))
    QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(100, 80))
    assert (selected[0].width(), selected[0].height()) == (80, 60)
    QTest.keyClick(overlay, Qt.Key.Key_Escape)
    QTest.mouseClick(overlay, Qt.MouseButton.RightButton)
    assert len(cancelled) == 2
    overlay.close()


class FakePreview(QWidget):
    def page(self):
        return Mock()

    def settings(self):
        return Mock()

    def setHtml(self, value):
        self.html = value


@pytest.fixture
def window(tmp_path):
    settings = QSettings(str(tmp_path / 'preferences.ini'), QSettings.Format.IniFormat)
    api = Mock()
    with patch('formula_ocr.app.create_preview', side_effect=lambda backend: FakePreview()), patch(
        'formula_ocr.app.GlobalHotkey', side_effect=lambda callback: GlobalHotkey(callback, api)
    ), patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=True), patch.object(
        QSystemTrayIcon, 'show'
    ), patch.object(QSystemTrayIcon, 'showMessage'):
        item = Window(settings)
        yield item
        item.timer.stop()
        item.capture_delay.stop()
        if item.capturing:
            item.capture.cancel()
        item.hotkey.close()
        item.tray.hide()
        item.hide()
        item.deleteLater()
        APP.processEvents()


def test_copy_disabled_by_default_and_edit_does_not_copy(window):
    APP.clipboard().setText('keep me')
    window.got_result('x^2')
    assert APP.clipboard().text() == 'keep me'
    window.settings.setValue('copy/enabled', True)
    window.editor.setPlainText('y^2')
    assert APP.clipboard().text() == 'keep me'
    window.error('failed recognition')
    assert APP.clipboard().text() == 'keep me'


@pytest.mark.parametrize('kind', CODE_FORMATS + [WORD_FORMAT])
def test_automatic_copy_selected_format(window, kind):
    window.settings.setValue('copy/enabled', True)
    window.settings.setValue('copy/format', kind)
    window.format.setCurrentText('equation')  # Independent of manual-copy selector.
    window.got_result(r'\frac{a}{b}')
    mime = APP.clipboard().mimeData()
    if kind == WORD_FORMAT:
        assert '<mfrac>' in mime.html()
        assert mime.hasFormat('application/mathml+xml')
    else:
        assert mime.text() == export_text(r'\frac{a}{b}', kind)
    assert '已自动复制' in window.status.text()


def test_conversion_failure_preserves_clipboard_and_result(window):
    APP.clipboard().setText('previous')
    window.settings.setValue('copy/enabled', True)
    window.settings.setValue('copy/format', 'MathML')
    with patch('formula_ocr.clipboard.export_text', side_effect=ValueError):
        window.got_result('x')
    assert APP.clipboard().text() == 'previous'
    assert window.editor.toPlainText() == 'x'
    assert '自动复制失败' in window.status.text()


def test_preferences_persist_and_conflict_is_not_saved(window):
    dialog = PreferencesDialog(window)
    assert dialog.hotkey.keySequence() == QKeySequence('Ctrl+Shift+A')
    assert not dialog.auto_copy.isChecked()
    dialog.hotkey.setKeySequence(QKeySequence('Ctrl+Alt+B'))
    dialog.auto_copy.setChecked(True)
    dialog.copy_format.setCurrentText(WORD_FORMAT)
    window.hotkey.api.RegisterHotKey.return_value = False
    with patch('formula_ocr.app.QMessageBox.warning'):
        dialog.save()
    assert not window.settings.value('copy/enabled', False, type=bool)
    window.hotkey.api.RegisterHotKey.return_value = True
    dialog.save()
    window.settings.sync()
    saved = QSettings(window.settings.fileName(), QSettings.Format.IniFormat)
    assert saved.value('capture/hotkey') == 'Ctrl+Alt+B'
    assert saved.value('copy/enabled', type=bool)
    assert saved.value('copy/format') == WORD_FORMAT
    reopened = PreferencesDialog(window)
    assert reopened.copy_format.currentText() == WORD_FORMAT
    reopened.reject()


@pytest.mark.parametrize('state', ['hidden', 'normal', 'minimized', 'maximized'])
def test_capture_cancel_keeps_result_and_success_starts_recognition(window, state):
    if state == 'normal':
        window.show()
    elif state == 'minimized':
        window.showMinimized()
    elif state == 'maximized':
        window.showMaximized()
    previous_state = window.windowState()
    previous_visibility = window.isVisible()
    window.editor.setPlainText('previous result')
    APP.clipboard().setText('previous clipboard')
    previous_policy = APP.quitOnLastWindowClosed()
    with patch.object(window.capture_delay, 'start') as schedule, patch.object(window, 'start_recognition') as recognize:
        window.start_capture()
        assert window.capturing
        assert not window.isVisible()
        schedule.assert_called_once()
        window.start_capture()  # Repeated hotkeys must not create extra overlays.
        schedule.assert_called_once()
        window.capture_cancelled()
        recognize.assert_not_called()
        assert window.editor.toPlainText() == 'previous result'
        assert APP.clipboard().text() == 'previous clipboard'
        assert APP.quitOnLastWindowClosed() == previous_policy
        assert window.isVisible() == previous_visibility
        assert window.windowState() == previous_state
        window.start_capture()
        image = QImage(80, 60, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        window.capture_completed(image)
        recognize.assert_called_once()
        assert window.png.startswith(b'\x89PNG')
        assert not window.capturing
        assert window.isVisible()
        assert not window.isMinimized()
        assert window.isMaximized() == (state == 'maximized')


def test_screenshot_error_and_busy_recognition(window):
    with patch.object(window.capture_delay, 'start') as schedule:
        window.worker = Mock()
        window.worker.isRunning.return_value = True
        window.start_capture()
        schedule.assert_not_called()
        window.worker = None
        window.start_capture()
        window.capture_failed('test failure')
        assert not window.capturing
        assert window.isVisible()
        assert '截图失败' in window.status.text()


@pytest.mark.parametrize('busy', [False, True])
def test_close_keeps_hotkey_and_recognition_alive_in_tray(window, busy):
    window.worker = Mock()
    window.worker.isRunning.return_value = busy
    window.editor.setPlainText('previous result')
    window.show()
    registered_id = window.hotkey.id
    with patch.object(APP, 'quit') as quit_app:
        window.close()
        assert not window.isVisible()
        assert not window.closing
        assert window.hotkey.id == registered_id
        window.hotkey.api.UnregisterHotKey.assert_not_called()
        quit_app.assert_not_called()
        window.got_result('x^2')
        window.worker.isRunning.return_value = False
        window.finished()
        assert not window.isVisible()
        window.tray_menu.actions()[0].trigger()
        assert window.isVisible()
        assert window.editor.toPlainText() == 'x^2'
        window.close()
        window.tray.showMessage.assert_called_once()


def test_tray_activation_restores_window_but_does_not_interrupt_capture(window):
    window.tray_activated(QSystemTrayIcon.ActivationReason.Context)
    assert not window.isVisible()
    window.tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert window.isVisible()
    window.showMinimized()
    window.tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
    assert not window.isMinimized()
    with patch.object(window.capture_delay, 'start'):
        window.tray_menu.actions()[1].trigger()
        assert window.capturing
        window.tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
        assert not window.isVisible()
        window.capture_cancelled()


@pytest.mark.parametrize('capture_pending', [False, True])
def test_explicit_exit_stops_hotkey_and_pending_capture(window, capture_pending):
    previous_policy = APP.quitOnLastWindowClosed()
    if capture_pending:
        window.start_capture()
        assert window.capture_delay.isActive()
    with patch.object(APP, 'quit') as quit_app:
        window.tray_exit_action.trigger()
        quit_app.assert_called_once()
        assert window.closing
        assert window.hotkey.id is None
        assert not window.capture_delay.isActive()
        assert not window.capturing
        assert not window.capture.overlays
        assert not window.isVisible()
        assert APP.quitOnLastWindowClosed() == previous_policy


def test_explicit_exit_waits_for_worker_then_quits(window):
    window.worker = Mock()
    window.worker.isRunning.return_value = True
    window.show()
    with patch.object(APP, 'quit') as quit_app:
        window.tray_exit_action.trigger()
        assert window.closing
        assert window.hotkey.id is None
        assert not window.tray_exit_action.isEnabled()
        assert '等待当前请求结束后退出' in window.status.text()
        quit_app.assert_not_called()
        assert not window.close()  # A running worker still owns the window.
        window.worker.isRunning.return_value = False
        window.finished()
        quit_app.assert_called_once()
        assert window.close()  # The final application quit must be able to close it.
        assert not window.isVisible()


def test_close_without_system_tray_exits(window):
    with patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=False), patch.object(APP, 'quit') as quit_app:
        window.show()
        window.close()
        quit_app.assert_called_once()
        assert window.closing
        assert window.hotkey.id is None
