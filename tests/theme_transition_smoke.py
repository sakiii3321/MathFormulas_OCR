"""Check the animated desktop composition in a visible Qt or WebView2 window."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QAbstractAnimation, QPoint, QRect, QSettings
from PySide6.QtGui import QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from formula_ocr.app import Window


def wait_for(check):
    deadline = time.monotonic() + 10
    while not check():
        if time.monotonic() >= deadline:
            raise AssertionError('Timed out waiting for theme transition')
        QTest.qWait(10)


def main(backend):
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    directory = Path(tempfile.mkdtemp(dir='.tmp', prefix='theme-wipe-')).resolve()
    settings = QSettings(str(directory/'prefs.ini'), QSettings.Format.IniFormat)
    settings.setValue('capture/hotkey', 'Ctrl+Alt+Shift+F10' if backend == 'qt' else 'Ctrl+Alt+Shift+F11')
    win = Window(settings, preview_backend=backend)
    win.resize(1050, 760)
    win.show()
    win.editor.setPlainText(r'\sum_{i=1}^n x_i = \frac{n(n+1)}{2}')
    surface, wipe = win.terrain, win.theme_wipe

    def capture():
        # Composite only this test window's layers, also when another app has focus.
        image = surface.grab()
        painter = QPainter(image)
        if backend == 'webview2':
            frames = []
            win.preview.capture_for_transition(frames.append)
            wait_for(lambda: bool(frames))
            frame = frames[0]
            assert frame and not frame.isNull()
            painter.drawPixmap(QRect(win.preview.mapTo(surface, QPoint()), win.preview.size()), frame, frame.rect())
        if wipe.isVisible():
            painter.drawPixmap(QPoint(), wipe.grab())
        painter.end()
        return image

    try:
        QTest.qWait(1600)
        for dark in (True, False):
            before = capture()
            win.night_switch.setChecked(dark)
            wait_for(lambda: wipe.motion.state() == QAbstractAnimation.State.Running)
            wipe.motion.pause()
            wipe.motion.setCurrentTime(wipe.motion.duration() // 2)
            QTest.qWait(200)
            middle = capture()
            assert not wipe.snapshot.isNull()
            wipe.motion.resume()
            wait_for(lambda: not wipe.isVisible())
            QTest.qWait(100)
            after = capture()
            middle.save(str(directory / ('night.png' if dark else 'day.png')))
            a, b, c = [s.toImage() for s in (before, middle, after)]
            for x, y, outgoing in ((.12, .80, False), (.85, .15, True),
                                   (.32, .57, False), (.91, .42, True)):
                px, py = round(a.width()*x), round(a.height()*y)
                first, mid, last = [i.pixelColor(px, py).lightness() for i in (a,b,c)]
                assert abs(first-last)>100 and abs(mid-(first if outgoing else last))<15, (x,y,first,mid,last)
            # Immediately on either side of the wipe there should be just the
            # two original theme colors, including where the edge crosses a pane.
            for y in (.22, .27, .50):
                py = round(a.height() * y)
                edge_x = round((a.width() - a.height()) / 2 + py)
                for offset, reference in ((-5, c), (5, a)):
                    px = edge_x + offset
                    assert abs(b.pixelColor(px, py).lightness() - reference.pixelColor(px, py).lightness()) < 10
            assert win.night_switch.isChecked() == settings.value('appearance/night', type=bool) == dark
            assert wipe.snapshot.isNull()
        win.night_switch.setChecked(True)
        win.night_switch.setChecked(False)
        QTest.qWait(750)
        assert not wipe.isVisible() and not win.applied_night
        win.close()
        prompt = win.close_prompt
        assert prompt.isVisible()
        prompt.grab().save(str(directory / 'close.png'))
        next(b for b in prompt.buttons() if b.text() == '转到后台').click()
        assert not win.isVisible() and win.hotkey.id is not None
        win.show_main_window()
        win.close()
        assert win.close_prompt.isVisible()
        print('PASS', backend, 'day/night diagonal frames, fast toggle, close prompt, tray restore;', directory, flush=True)
    finally:
        win.quit_application()


if __name__ == '__main__':
    main(sys.argv[1])
