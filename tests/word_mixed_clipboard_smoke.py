"""Validate HTML MathML paste into an isolated installed Word instance."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import win32com.client
from PySide6.QtCore import QMimeData
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from formula_ocr.clipboard import copy_mixed
from formula_ocr.mixed import MIXED_EXAMPLE, MIXED_WORD, from_markdown

app = QApplication([])
backup = QMimeData()
original = app.clipboard().mimeData()
for fmt in original.formats():
    backup.setData(fmt, original.data(fmt))
word = win32com.client.DispatchEx('Word.Application')
word.Visible = False
word.DisplayAlerts = 0
document = None
try:
    mixed = from_markdown(MIXED_EXAMPLE)
    picture = QImage(80, 40, QImage.Format.Format_RGB32)
    picture.fill(0xff00ff00)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    picture.save(buffer, 'PNG')
    mixed.assets['figure-1.png'] = bytes(buffer.data())
    mixed.blocks.append({'type': 'image', 'asset': 'figure-1.png'})
    copy_mixed(mixed, MIXED_WORD)
    app.processEvents()
    document = word.Documents.Add()
    document.Content.PasteSpecial(DataType=10)
    text = document.Content.Text
    assert 'Bayesian regularization' in text
    assert '(4)' in text and '(5)' in text and '(6)' in text
    assert document.OMaths.Count > 10, f'Only {document.OMaths.Count} native equations imported'
    assert document.InlineShapes.Count == 1
    assert document.Tables.Count == 0
    numbered = []
    for p in document.Paragraphs:
        line = p.Range.Text.rstrip('\r')
        if line.startswith('\t'):
            assert p.Range.OMaths.Count == 1
            assert line.count('\t') == 2
            stops = [(s.Alignment, s.Position) for s in p.Format.TabStops]
            # Word may also list its default left stops after the final custom stop.
            assert stops[:2] == [(1, 207.0), (2, 414.0)], stops
            numbered.append(line.rsplit('\t', 1)[1])
    assert numbered == ['(4)', '(5)', '(6)'], numbered
    document.ExportAsFixedFormat(str(Path('artifacts/mixed-clipboard.pdf').resolve()), 17)
    print('PASS: Word HTML paste contains prose, numbers and', document.OMaths.Count, 'native editable equations.')
finally:
    if document is not None:
        document.Close(False)
    word.Quit()
    app.clipboard().setMimeData(backup)
