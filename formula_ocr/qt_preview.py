from PySide6.QtWebEngineCore import QWebEngineScript, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from .preview import FIT_FORMULA_SCRIPT, preview_theme_script


class QtPreview(QWebEngineView):
    def __init__(self):
        super().__init__()
        self._night = None
        self.loadFinished.connect(self._restore_theme)

    def set_preview_theme(self, night):
        self._night = night
        self._restore_theme(True)

    def _restore_theme(self, loaded):
        if loaded and self._night is not None:
            self.page().runJavaScript(preview_theme_script(self._night), QWebEngineScript.ScriptWorldId.ApplicationWorld)


def create_qt_preview():
    view = QtPreview()
    view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, False)
    view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
    fit = QWebEngineScript()
    fit.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
    fit.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    fit.setSourceCode(FIT_FORMULA_SCRIPT)
    view.page().scripts().insert(fit)
    return view
