"""Select the preview engine without importing the other distribution's engine."""


def create_preview(backend):
    if backend == "webview2":
        from .webview2_preview import WebView2Preview
        return WebView2Preview()
    if backend == "qt":
        from .qt_preview import create_qt_preview
        return create_qt_preview()
    raise ValueError(f"Unknown preview engine: {backend}")
