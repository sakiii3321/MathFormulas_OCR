"""Local HTML/MathML preview using the shared Windows WebView2 Runtime."""
import html
import json
import ctypes
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QEvent, QStandardPaths, Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from sideview import NativeWebView, NativeWebViewError

RUNTIME_URL = "https://developer.microsoft.com/microsoft-edge/webview2/#download-section"


class DpiWebView(NativeWebView):
    """SideView 0.4 expects physical HWND bounds; Qt reports logical widget sizes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ready.connect(self._sync_native_geometry)

    def _sync_native_geometry(self):
        if not self._created:
            return
        scale = self.devicePixelRatioF()
        self._backend.resize(self._handle, round(self.width() * scale), round(self.height() * scale))
        if self._native_ready:
            get_dpi = ctypes.windll.user32.GetDpiForWindow
            get_dpi.argtypes = [wintypes.HWND]
            get_dpi.restype = wintypes.UINT
            native_scale = (get_dpi(int(self.winId())) or 96) / 96
            # Also honor an explicit QT_SCALE_FACTOR, in addition to the monitor DPI.
            self.set_zoom_factor(scale / native_scale)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_native_geometry()

    def event(self, event):
        result = super().event(event)
        if event.type() == QEvent.Type.DevicePixelRatioChange and hasattr(self, '_created'):
            self._sync_native_geometry()
        return result


class WebView2Preview(QWidget):
    loadFinished = Signal(bool)

    def __init__(self, parent=None, profile_path=None):
        super().__init__(parent)
        self._callbacks = {}
        self._request_id = 0
        self._view = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.message = QLabel(self)
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setTextFormat(Qt.TextFormat.RichText)
        self.message.setOpenExternalLinks(True)
        layout.addWidget(self.message)
        self.message.hide()
        if profile_path is None:
            profile_path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)) / "FormulaOCR" / "WebView2"
        try:
            self._view = DpiWebView(self, user_data_folder=str(profile_path))
            self._view.set_default_context_menu_enabled(False)
            self._view.set_devtools_enabled(False)
            self._view.navigationFinished.connect(self._loaded)
            self._view.navigationFailed.connect(self._failed)
            self._view.scriptMessageReceived.connect(self._script_result)
            layout.addWidget(self._view)
        except NativeWebViewError as exc:
            self._failed(str(exc))
        QApplication.instance().aboutToQuit.connect(self.dispose)

    def page(self):
        return self

    def setBackgroundColor(self, color):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, color)
        self.setPalette(palette)
        self.setAutoFillBackground(True)

    def setHtml(self, markup):
        if self._view is not None:
            try:
                self._view.set_html(markup)
            except NativeWebViewError as exc:
                self._failed(str(exc))

    def setUrl(self, url):
        if not url.isLocalFile():
            raise ValueError("预览仅支持本地生成的文件。")
        if self._view is not None:
            try:
                self._view.navigate(url.toString())
            except NativeWebViewError as exc:
                self._failed(str(exc))

    def _loaded(self, _url):
        self.message.hide()
        self._view.show()
        self.loadFinished.emit(True)

    def _failed(self, message):
        if self._view is not None:
            self._view.hide()
        self.message.setText(
            "WebView2 预览未能启动或加载。<br>"
            f'请安装或修复 <a href="{RUNTIME_URL}">Microsoft WebView2 Runtime</a> 后重启程序。<br>'
            "识别、编辑、复制及导出仍可使用。<br><br>"
            + html.escape(message)
        )
        self.message.show()
        self.loadFinished.emit(False)

    def runJavaScript(self, script, callback=None):
        """Evaluate a host-supplied expression; page scripts remain blocked by CSP."""
        if self._view is None:
            raise RuntimeError("WebView2 预览不可用。")
        if callback is None:
            self._view.eval_js(script)
            return
        self._request_id += 1
        request_id = self._request_id
        self._callbacks[request_id] = callback
        try:
            self._view.eval_js(
                "(() => { const value = (" + script + ");"
                "window.chrome.webview.postMessage(JSON.stringify({"
                f'formulaOcrRequest:{request_id}, value:value'
                "})); })()"
            )
        except NativeWebViewError:
            self._callbacks.pop(request_id, None)
            raise

    def _script_result(self, text):
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            return
        if isinstance(payload, dict):
            callback = self._callbacks.pop(payload.get("formulaOcrRequest"), None)
            if callback is not None:
                callback(payload.get("value"))

    def toPlainText(self, callback):
        self.runJavaScript("document.body.innerText", callback)

    def dispose(self):
        self._callbacks.clear()
        if self._view is not None:
            self._view.dispose()
