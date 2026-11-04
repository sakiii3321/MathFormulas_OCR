from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView


def create_qt_preview():
    view = QWebEngineView()
    view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, False)
    view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
    return view
