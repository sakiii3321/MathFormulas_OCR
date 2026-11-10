"""Shared formula layout and preview engine selection."""
import json

from .theme import preview_css

DEFAULT_MIN_FONT_PX = 16
MIN_FONT_PX = 12
NORMAL_FONT_PX = 27


def preview_theme_script(night):
    css = json.dumps(preview_css(night))
    return f"""(() => {{
        if (!document.head) return;
        let style = document.getElementById('preview-theme');
        if (!style) {{
            style = document.createElement('style');
            style.id = 'preview-theme';
            document.head.append(style);
        }}
        style.textContent = {css};
    }})()"""


def formula_preview_html(content, theme_css, minimum):
    minimum = max(MIN_FONT_PX, min(NORMAL_FONT_PX, minimum))
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<style>
{theme_css}
html,body{{height:100%;margin:0;box-sizing:border-box}}
#formula-viewport{{height:100%;display:flex;overflow:auto}}
#formula-viewport > math{{flex:none;width:max-content;margin:auto;
    font:{NORMAL_FONT_PX}px "Cambria Math",serif}}
#formula-viewport > p{{margin:auto;font:14px sans-serif}}
</style></head><body>
<div id="formula-viewport" data-min-font="{minimum}" data-normal-font="{NORMAL_FONT_PX}">{content}</div>
</body></html>"""


# Installed by the host, only in the local single-formula layout. Native MathML
# metrics include fractions, limits, and row spacing that line counts cannot predict.
FIT_FORMULA_SCRIPT = """(() => {
    const frame = document.getElementById('formula-viewport');
    const math = frame?.querySelector(':scope > math');
    if (!math || frame.dataset.fitReady) return;
    frame.dataset.fitReady = '1';
    function fit() {
        const bounds = frame.getBoundingClientRect();
        if (!bounds.width || !bounds.height) return;
        function fits(size) {
            math.style.fontSize = size + 'px';
            const box = math.getBoundingClientRect();
            return box.width <= bounds.width && box.height <= bounds.height;
        }
        let low = Number(frame.dataset.minFont);
        let high = Number(frame.dataset.normalFont);
        if (fits(high)) return;
        while (low < high) {
            const mid = Math.ceil((low + high) / 2);
            if (fits(mid)) low = mid;
            else high = mid - 1;
        }
        math.style.fontSize = low + 'px';
    }
    fit();
    window.addEventListener('resize', fit);
    document.fonts.ready.then(fit);
})()"""


def create_preview(backend):
    if backend == "webview2":
        from .webview2_preview import WebView2Preview
        return WebView2Preview()
    if backend == "qt":
        from .qt_preview import create_qt_preview
        return create_qt_preview()
    raise ValueError(f"Unknown preview engine: {backend}")
