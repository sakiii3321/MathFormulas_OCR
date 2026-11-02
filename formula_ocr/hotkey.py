"""Windows global shortcut registration, owned by the Qt GUI thread."""
import ctypes
from ctypes import wintypes
from itertools import count
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

DEFAULT_HOTKEY = "Ctrl+Shift+A"
_IDS = count(0x4000)


def parse_hotkey(text):
    sequence = QKeySequence(text, QKeySequence.SequenceFormat.PortableText)
    if sequence.count() != 1:
        raise ValueError("请设置单组快捷键，例如 Ctrl+Shift+A。")
    combination = sequence[0]
    key = combination.key().value
    flags = combination.keyboardModifiers()
    if not flags & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
        raise ValueError("截图快捷键须包含 Ctrl 或 Alt，避免影响正常输入。")
    allowed = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier
    if flags.value & ~allowed.value:
        raise ValueError("请使用 Ctrl、Alt、Shift 组合，不使用 Windows 键。")
    if ord('A') <= key <= ord('Z') or ord('0') <= key <= ord('9'):
        vk = key
    elif Qt.Key.Key_F1.value <= key <= Qt.Key.Key_F24.value:
        vk = 0x70 + key - Qt.Key.Key_F1.value
        if vk == 0x7B:  # Windows reserves F12 for the debugger.
            raise ValueError("Windows 保留了 F12，请选择其他按键。")
    else:
        raise ValueError("请使用字母、数字或 F1–F24（F12 除外）作为快捷键主键。")
    modifiers = 0
    for qt_flag, win_flag in [(Qt.KeyboardModifier.ControlModifier, 2),
                              (Qt.KeyboardModifier.AltModifier, 1),
                              (Qt.KeyboardModifier.ShiftModifier, 4)]:
        if flags & qt_flag:
            modifiers |= win_flag
    return sequence.toString(QKeySequence.SequenceFormat.PortableText), modifiers, vk


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(self, callback, api=None):
        super().__init__()
        self.callback = callback
        self.id = None
        self.sequence = ""
        self.api = api
        if api is None and sys.platform == "win32":
            self.api = ctypes.WinDLL("user32", use_last_error=True)
            self.api.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self.api.RegisterHotKey.restype = wintypes.BOOL
            self.api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            self.api.UnregisterHotKey.restype = wintypes.BOOL
        QApplication.instance().installNativeEventFilter(self)

    def register(self, text):
        sequence, modifiers, vk = parse_hotkey(text)
        if sequence == self.sequence and self.id is not None:
            return sequence
        if self.api is None:
            raise ValueError("全局快捷键仅支持 Windows；仍可点击截图按钮。")
        new_id = next(_IDS)
        if not self.api.RegisterHotKey(None, new_id, modifiers | 0x4000, vk):
            raise ValueError(f"快捷键 {sequence} 已被占用或无法注册，请更换组合。")
        # Keep the working shortcut until the replacement was successfully registered.
        if self.id is not None:
            self.api.UnregisterHotKey(None, self.id)
        self.id, self.sequence = new_id, sequence
        return sequence

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and self.id is not None and msg.wParam == self.id:
                QTimer.singleShot(0, self.callback)
                return True, 0
        return False, 0

    def close(self):
        if self.id is not None:
            self.api.UnregisterHotKey(None, self.id)
            self.id = None
        QApplication.instance().removeNativeEventFilter(self)
