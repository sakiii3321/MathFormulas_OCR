from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtWidgets import QApplication

from .core import export_text, mathml

CODE_FORMATS = ["LaTeX", "$ … $", "$$ … $$", r"\[ … \]", "equation", "MathML"]
WORD_FORMAT = "Word 公式（MathML）"
COPY_FORMATS = CODE_FORMATS + [WORD_FORMAT]


def copy_formula(latex, kind):
    """Convert completely before replacing the clipboard (including automatic copy)."""
    if kind != WORD_FORMAT:
        QApplication.clipboard().setText(export_text(latex, kind))
        return
    markup = mathml(latex)
    mime = QMimeData()
    mime.setText(markup)
    mime.setHtml('<html><body>' + markup + '</body></html>')
    mime.setData('application/mathml+xml', QByteArray(markup.encode("utf-8")))
    mime.setData('application/x-qt-windows-mime;value="MathML"', QByteArray(markup.encode("utf-8") + b'\x00'))
    QApplication.clipboard().setMimeData(mime)


def copy_mixed(document, kind):
    from .mixed import MIXED_WORD, export_mixed_text, to_html, to_markdown
    if kind != MIXED_WORD:
        QApplication.clipboard().setText(export_mixed_text(document, kind))
        return
    # Mixed content is ONE HTML document, not a math-specific clipboard payload
    # (which Word can prioritize over HTML and thus drop surrounding paragraphs).
    markup = to_html(document, word=True)
    mime = QMimeData()
    mime.setHtml(markup)
    mime.setText(to_markdown(document))
    QApplication.clipboard().setMimeData(mime)
