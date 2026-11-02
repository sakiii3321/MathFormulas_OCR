"""QA fallback: render this project's fixture using an isolated Word instance."""
from pathlib import Path
import sys

import win32com.client

path = Path(sys.argv[1]).resolve()
out = path.with_suffix('.pdf')
word = win32com.client.DispatchEx('Word.Application')
word.Visible = False
word.DisplayAlerts = 0
document = None
try:
    document = word.Documents.Open(str(path), ReadOnly=True, AddToRecentFiles=False)
    document.ExportAsFixedFormat(str(out), 17)
    print('Rendered DOCX with Word:', out)
finally:
    if document is not None:
        document.Close(False)
    word.Quit()
