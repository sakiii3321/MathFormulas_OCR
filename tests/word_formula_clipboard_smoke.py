"""Run with desktop Word installed to check normal and HTML equation paste."""
import ctypes
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

import win32com.client
from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from formula_ocr.clipboard import copy_formula, WORD_FORMAT
from formula_ocr.word_math import OM
from test_mathtype import FLOW_FORMULAS


def flush_clipboard(app):
    for attempt in range(40):
        app.processEvents()
        if ctypes.windll.ole32.OleFlushClipboard() == 0:
            return
        time.sleep(0.05)
    raise RuntimeError('Could not materialize the test clipboard')


def wait_for_formula_clipboard(app, clipboard):
    """Let Qt/OLE finish before synchronous COM paste blocks this GUI thread.

    OleFlushClipboard succeeding alone can precede transient empty MIME reads.
    This gate only waits for the original payload; it never retries Word.Paste
    or substitutes a different paste route.
    """
    required = ('text/plain', 'text/html', 'application/mathml+xml',
                'application/x-qt-windows-mime;value="MathML"',
                'application/x-qt-windows-mime;value="MathML Presentation"')
    previous_sequence = None
    stable = 0
    for attempt in range(40):
        app.processEvents()
        time.sleep(0.05)
        sequence = ctypes.windll.user32.GetClipboardSequenceNumber()
        mime = clipboard.mimeData()
        ready = mime is not None and all(mime.data(fmt).size() > 0 for fmt in required)
        ready = ready and sequence == ctypes.windll.user32.GetClipboardSequenceNumber()
        stable = stable + 1 if ready and sequence == previous_sequence else int(ready)
        previous_sequence = sequence
        if stable >= 3:
            return
    raise RuntimeError('Formula clipboard did not become ready within the bounded wait')


app = QApplication([])
clipboard = app.clipboard()
backup = QMimeData()
original = clipboard.mimeData()
if original:
    for fmt in original.formats():
        backup.setData(fmt, original.data(fmt))
word = win32com.client.DispatchEx('Word.Application')
word.Visible = False
word.DisplayAlerts = 0
print(f'Word version={word.Version} build={word.Build}', flush=True)
try:
    for repeat in range(2):
        for index, latex in enumerate(FLOW_FORMULAS):
            for route in ('normal', 'html'):
                document = word.Documents.Add()
                try:
                    copy_formula(latex, WORD_FORMAT)
                    flush_clipboard(app)
                    wait_for_formula_clipboard(app, clipboard)
                    if route == 'normal':
                        document.Content.Paste()
                    else:
                        document.Content.PasteSpecial(DataType=10)
                    assert document.OMaths.Count == 1, (index, route, document.Content.Text)
                    xml = ET.fromstring(document.Content.WordOpenXML)
                    assert len(xml.findall('.//' + OM + 'f')) == 3
                    if index == 1:
                        assert xml.find('.//' + OM + 'accPr/' + OM + 'chr').get(OM + 'val') == '\u0307'
                    if index == 2:
                        assert xml.find('.//' + OM + 'barPr/' + OM + 'pos').get(OM + 'val') == 'top'
                    print(f'PASS repeat={repeat + 1} formula={index + 1} paste={route}', flush=True)
                finally:
                    document.Close(False)
finally:
    word.Quit()
    clipboard.setMimeData(backup)
    flush_clipboard(app)
