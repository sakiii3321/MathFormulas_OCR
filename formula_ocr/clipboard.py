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
    markup = mathml(latex, for_word=True)
    mime = QMimeData()
    mime.setText(markup)
    if '<malignmark' in markup:
        from .mixed import office_html_math
        # Browsers render the two physical columns; Word gets an editable equation array.
        browser = mathml(latex)
        try:
            office = office_html_math(latex, True)
            rich = ('<!--[if gte msEquation 12]>' + office + '<![endif]-->'
                    '<!--[if !msEquation]><!-->' + browser + '<!--<![endif]-->')
        except ValueError:
            rich = browser
        mime.setHtml('<html xmlns:m="http://schemas.microsoft.com/office/2004/12/omml"><body>'
                     + rich + '</body></html>')
    else:
        mime.setHtml('<html><body>' + markup + '</body></html>')
    mime.setData('application/mathml+xml', QByteArray(markup.encode("utf-8")))
    office_data = QByteArray((markup + '\0').encode('utf-16-le'))
    for name in ('MathML', 'MathML Presentation'):
        mime.setData(f'application/x-qt-windows-mime;value="{name}"', office_data)
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
