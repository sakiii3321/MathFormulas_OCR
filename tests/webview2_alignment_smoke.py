"""Measure real WebView2 layout for aligned formulas; no API or clipboard access."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from latex2mathml.converter import convert
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from formula_ocr.core import mathml
from formula_ocr.mixed import from_markdown, to_html
from formula_ocr.webview2_preview import WebView2Preview
from test_core import BOUNDARY_CONDITIONS

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
preview = WebView2Preview(profile_path=Path('.tmp/alignment-webview-profile').resolve())
preview.resize(1000, 720)
preview.show()
baseline = convert(BOUNDARY_CONDITIONS.replace('aligned', 'align*'), display='block')
mixed = to_html(from_markdown('Boundary conditions\n\n$$\n' + BOUNDARY_CONDITIONS + '\n$$'))
markup = ('<!doctype html><meta charset="utf-8"><style>'
          'body{background:white;color:black;margin:24px}math{font-size:27px;font-family:"Cambria Math",serif}'
          '#baseline{position:absolute;left:-10000px;width:900px}</style>'
          '<section id="formula">' + mathml(BOUNDARY_CONDITIONS) + '</section>'
          '<section id="mixed">' + mixed + '</section>'
          '<section id="baseline">' + baseline + '</section>')
preview.setHtml(markup)
finished = False


def inspect(data):
    global finished
    if finished or not data or not data.get('formula'):
        return
    try:
        for name in ('formula', 'mixed'):
            rows = data[name]
            assert len(rows) == 4, data
            for key in ('lhsRight', 'equalsLeft', 'conditionLeft'):
                positions = [row[key] for row in rows]
                assert max(positions) - min(positions) < 1, (name, key, positions)
            assert all(0 <= row['equalsLeft'] - row['lhsRight'] < 16 for row in rows), rows
        before = [row['lhsRight'] for row in data['baseline']]
        assert max(before) - min(before) > 20, before
        output = Path('.tmp/alignment-preview-webview2.png')
        preview._view.captureCompleted.connect(lambda _request, png: output.write_bytes(png))
        preview._view.capture_frame()
        print('PASS WebView2: aligned and mixed previews align all four equations and conditions; original output reproduces the defect.', flush=True)
        print('PREVIEW_IMAGE=' + str(output.resolve()), flush=True)
        finished = True
        poll.stop()
        QTimer.singleShot(500, lambda: app.exit(0))
    except Exception:
        finished = True
        poll.stop()
        import traceback
        traceback.print_exc()
        print(data, flush=True)
        app.exit(1)


def check():
    script = """Object.fromEntries(['formula','mixed','baseline'].map(id=>{
      const table=document.querySelector('#'+id+' math mtable');
      return [id,table?[...table.children].map(row=>{
        const cells=[...row.children];
        const range=document.createRange();range.selectNodeContents(cells[0]);
        return {alignment:getComputedStyle(cells[0]).textAlign, cellRight:cells[0].getBoundingClientRect().right, lhsRight:range.getBoundingClientRect().right,
          equalsLeft:cells[1].querySelector('mo').getBoundingClientRect().left,
          conditionLeft:cells[3].querySelector('mtext').getBoundingClientRect().left};
      }):[]];}))"""
    if preview._view and preview._view._native_ready:
        preview.runJavaScript(script, inspect)


poll = QTimer()
poll.setInterval(400)
poll.timeout.connect(check)
poll.start()
QTimer.singleShot(20000, lambda: app.exit(2))
sys.exit(app.exec())
