"""Check real MathML sizing and overflow in each shipping renderer. Run with qt or webview2."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from formula_ocr.core import mathml
from formula_ocr.preview import create_preview, formula_preview_html
from formula_ocr.theme import preview_css


def main(backend):
    app = QApplication([])
    if backend == 'webview2':
        from formula_ocr.webview2_preview import WebView2Preview
        view = WebView2Preview(profile_path=Path('.tmp/fit-webview2-profile').resolve())
        evaluate = view.runJavaScript
    else:
        from PySide6.QtWebEngineCore import QWebEngineScript
        view = create_preview(backend)
        def evaluate(script, callback):
            view.page().runJavaScript(script, QWebEngineScript.ScriptWorldId.ApplicationWorld, callback)

    metrics = """JSON.stringify((() => {
        const f = document.querySelector('#formula-viewport[data-fit-ready]');
        if (!f) return null;
        const math = f.querySelector('math'), r = math.getBoundingClientRect(), b = f.getBoundingClientRect();
        return {size:parseFloat(getComputedStyle(math).fontSize), h:r.height, w:r.width,
                rows:math.querySelectorAll('mtr').length, min:Number(f.dataset.minFont),
                x:r.left-b.left+f.scrollLeft, y:r.top-b.top+f.scrollTop,
                dx:f.scrollWidth-f.clientWidth, dy:f.scrollHeight-f.clientHeight};
    })())"""

    def wait_for(check, *, script=metrics):
        deadline = time.monotonic() + 12
        last = None
        while time.monotonic() < deadline:
            result = []
            QTest.qWait(60)
            if backend == 'webview2' and not view._view._native_ready:
                continue
            evaluate(script, result.append)
            while not result and time.monotonic() < deadline:
                QTest.qWait(10)
            if result and result[0]:
                last = json.loads(result[0])
                if last and check(last):
                    return last
        raise AssertionError((backend, last))

    def render(latex, minimum=16):
        view.setHtml(formula_preview_html(mathml(latex), preview_css(False), minimum))

    view.resize(820, 650)
    view.show()
    try:
        lines = r'\\'.join(r'a_{%d} &= \frac{t}{1+t^2}' % i for i in range(6))
        render(r'\begin{aligned}' + lines + r'\end{aligned}')
        original = wait_for(lambda d: d['rows'] == 6 and d['size'] == 27 and d['dx'] == d['dy'] == 0)
        view.resize(820, round(original['h'] * .8) + 28)
        compact = wait_for(lambda d: 16 < d['size'] < 27 and d['dx'] == d['dy'] == 0)
        view.resize(820, 105)
        wait_for(lambda d: d['size'] == 16 and d['dy'] > 0 and 0 <= d['y'] <= 1)
        view.resize(820, 650)
        wait_for(lambda d: d['size'] == 27 and d['dx'] == d['dy'] == 0)
        render('+'.join(['a'] * 15), minimum=20)
        wide = wait_for(lambda d: d['rows'] == 0 and d['min'] == 20 and d['size'] == 27)
        view.resize(round(wide['w'] * .88) + 40, 200)
        wait_for(lambda d: 20 < d['size'] < 27 and d['dx'] == d['dy'] == 0)
        view.resize(195, 130)
        wait_for(lambda d: d['size'] == 20 and d['dx'] > 0 and 0 <= d['x'] <= 1)
        # Verify the far edge of overflowing content can actually be reached.
        wait_for(lambda d: d['right'] <= d['edge'] + 1, script="""JSON.stringify((() => {
            const f = document.getElementById('formula-viewport'); f.scrollLeft = f.scrollWidth;
            return {right:f.firstElementChild.getBoundingClientRect().right,
                    edge:f.getBoundingClientRect().left+f.clientWidth};
        })())""")
        render('x^2')
        wait_for(lambda d: d['min'] == 16 and d['size'] == 27 and d['dx'] == d['dy'] == 0)
        print(f"PASS {backend}: six rows fit at {compact['size']}px, width fit, font floor, scroll and regrowth")
    finally:
        view.close()
        if backend == 'webview2':
            view.dispose()
        app.processEvents()


if __name__ == '__main__':
    main(sys.argv[1])
