"""Field-manual styling for the desktop shell."""
from pathlib import Path
from string import Template

from PySide6.QtCore import QByteArray, QEasingCurve, QPointF, QRect, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListView, QPushButton,
                               QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

ASSETS = Path(__file__).resolve().parent / "assets"

# Each token has a daylight and a night value. The yellow signal and its ink
# stay the same in both modes, including in the custom-painted selection tick.
_TONES = {
    "shell": ("#e8e8e2", "#131612"), "rail": ("#e6e6df", "#20241f"),
    "paper": ("#f2f2ec", "#242822"), "sheet": ("#fbfbf7", "#191d19"),
    "ink": ("#161814", "#edf0e7"), "muted": ("#565a50", "#bcc3b5"),
    "line": ("#b8bbb0", "#62695c"), "hairline": ("#d2d4ca", "#464d41"),
    "button": ("#f9faf4", "#31372e"), "over": ("#e7e9df", "#40483b"),
    "down": ("#d3d6c8", "#4a5143"), "edge": ("#777d6c", "#8b9782"),
    "focus": ("#353a2e", "#e5e2a3"), "subtleInk": ("#393f33", "#d7ddcf"),
    "strong": ("#252821", "#3d4739"), "strongOver": ("#3b4134", "#515d49"),
    "strongDown": ("#141710", "#30392d"),
    "disabled": ("#e4e6dc", "#292d27"), "dim": ("#797d71", "#a0a599"),
    "tab": ("#dcded4", "#30362c"), "openField": ("#edf0df", "#373e2c"),
    "hoverField": ("#f3f5e9", "#30372a"), "note": ("#64685c", "#bbc2b2"),
    "warning": ("#b45309", "#ffc58c"), "track": ("#d8dace", "#414738"),
}


def theme_colors(night):
    return {role: pair[int(night)] for role, pair in _TONES.items()}


def field_map(night):
    data = (ASSETS / "field-map.svg").read_bytes()
    if night:
        for day, dark in [(b"#e6e6df", b"#171b17"), (b"#bdc0b6", b"#343a33"),
                          (b"#a5a79e", b"#454c40"), (b"#65685f", b"#abb39f"),
                          (b"#777a70", b"#909a84"), (b"#fff500", b"#b3ad24")]:
            data = data.replace(day, dark)
    return QByteArray(data)


def apply_theme(app, night):
    colors = theme_colors(night)
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if night else Qt.ColorScheme.Light)
    palette = app.style().standardPalette()
    role = QPalette.ColorRole
    for name, token in [(role.Window, "shell"), (role.WindowText, "ink"), (role.Base, "sheet"),
                        (role.AlternateBase, "over"), (role.Text, "ink"), (role.Button, "button"),
                        (role.ButtonText, "ink"), (role.PlaceholderText, "note"), (role.Light, "edge"),
                        (role.Midlight, "hairline"), (role.Mid, "line"), (role.Dark, "rail"),
                        (role.ToolTipBase, "paper"), (role.ToolTipText, "ink")]:
        palette.setColor(name, QColor(colors[token]))
    palette.setColor(role.Highlight, QColor("#fff500"))
    palette.setColor(role.HighlightedText, QColor("#101110"))
    for name in (role.Text, role.WindowText, role.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, name, QColor(colors["dim"]))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(night))


def preview_css(night):
    colors = theme_colors(night)
    return (f":root{{color-scheme:{'dark' if night else 'light'}}}"
            f"body{{background:{colors['sheet']};color:{colors['ink']};padding:14px 20px}}"
            f".preview-note{{color:{colors['note']}}}.formula-error{{color:{colors['warning']}}}")

_OPTION_HINTS = {
    "LaTeX": "LaTeX 源码", "$ … $": "行内公式", "$$ … $$": "块级公式",
    r"\[ … \]": "独立公式", "equation": "编号公式环境", "MathML": "公式标记源码",
    "Word 公式（MathML）": "粘贴为 Word 公式", "Markdown": "正文与公式标记",
    "HTML": "网页图文源码", "Word 图文（富文本）": "正文与可编辑公式",
    "自定义兼容接口": "自定义服务地址和模型",
}


class _OptionRow(QStyledItemDelegate):
    """Highlight the browsing row separately from the committed choice."""
    def sizeHint(self, option, index):
        label = index.data() or ""
        hint = _OPTION_HINTS.get(label, "")
        metrics = option.fontMetrics
        width = max(metrics.horizontalAdvance(label), metrics.horizontalAdvance(hint)) + 57
        height = metrics.height() * (2 if hint else 1) + (13 if hint else 16)
        return QSize(width, height)

    def paint(self, painter, option, index):
        label = index.data() or ""
        hint = _OPTION_HINTS.get(label)
        chosen = index.row() == self.parent().currentIndex()
        active = option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver)
        row = option.rect.adjusted(3, 1, -3, -1)
        painter.save()
        if active:
            painter.fillRect(row, option.palette.color(QPalette.ColorRole.AlternateBase))
        text_box = row.adjusted(11, 3, -31, -3)
        line = option.fontMetrics.height()
        if hint:
            text_box.setTop(row.center().y() - line)
            text_box.setHeight(line)
        painter.setPen(option.palette.color(QPalette.ColorRole.Text))
        painter.drawText(text_box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         option.fontMetrics.elidedText(label, Qt.TextElideMode.ElideRight, text_box.width()))
        if hint:
            font = option.font
            font.setPixelSize(11)
            painter.setFont(font)
            painter.setPen(option.palette.color(QPalette.ColorRole.PlaceholderText))
            hint_box = text_box.translated(0, line)
            painter.drawText(hint_box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText(hint, Qt.TextElideMode.ElideRight, hint_box.width()))
        if chosen:
            tick = QRect(row.right() - 24, row.center().y() - 7, 15, 15)
            painter.fillRect(tick, QColor("#fff500"))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("#26291f"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            x, y = tick.x(), tick.y()
            painter.drawLine(QPointF(x+3.5, y+7.5), QPointF(x+6.5, y+10.5))
            painter.drawLine(QPointF(x+6.5, y+10.5), QPointF(x+11.5, y+4.5))
        painter.restore()


class FieldSelect(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        view = QListView()
        view.setObjectName("optionList")
        view.setMouseTracking(True)
        view.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setView(view)
        self.setItemDelegate(_OptionRow(self))

    def showPopup(self):
        # Reserve the tick column even when the closed selector is quite narrow.
        self.view().setMinimumWidth(max(176, self.width(), self.view().sizeHintForColumn(0) + 8))
        super().showPopup()
        if self.currentIndex() >= 0:
            current = self.model().index(self.currentIndex(), self.modelColumn(), self.rootModelIndex())
            self.view().setCurrentIndex(current)


class ActionButton(QPushButton):
    """A short hover stroke sits on top of the standard Qt button interaction."""
    def __init__(self, text):
        super().__init__(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rollover = QVariantAnimation(self)
        self._rollover.setStartValue(0.0)
        self._rollover.setEndValue(1.0)
        self._rollover.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._rollover.valueChanged.connect(lambda _: self.update())

    def _animate(self, target):
        value = float(self._rollover.currentValue() or 0.0)
        self._rollover.stop()
        self._rollover.setStartValue(value)
        self._rollover.setEndValue(target)
        duration = 125 if self.style().styleHint(QStyle.StyleHint.SH_Widget_Animate) else 0
        self._rollover.setDuration(round(duration * abs(value - target)))
        self._rollover.start()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._animate(1.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._animate(0.0)

    def paintEvent(self, event):
        super().paintEvent(event)
        amount = float(self._rollover.currentValue() or 0.0)
        if not self.isEnabled() or amount <= 0:
            return
        painter = QPainter(self)
        if self.objectName() == "navAction":
            h = round((self.height() - 12) * amount)
            painter.fillRect(1, (self.height() - h) // 2, 3, h, QColor("#b3a900"))
        else:
            color = "#25271f" if self.objectName() == "primary" else "#c4ba00"
            painter.fillRect(1, self.height() - 3, round((self.width() - 2) * amount), 2, QColor(color))

_GLYPHS = {
    "capture": "M8 3H3v5 M16 3h5v5 M21 16v5h-5 M8 21H3v-5",
    "image": "M3 5h18v14H3z M3 16l5-5 4 4 3-3 6 6 M16 9h.1",
    "paste": "M8 5H5v16h14V5h-3 M9 3h6v4H9z M9 12h6 M9 16h4",
    "settings": "M3 6h9 M16 6h5 M3 12h2 M9 12h12 M3 18h11 M18 18h3 M12 4v4 M8 10v4 M15 16v4",
    "api": "M4 8l-3 4 3 4 M20 8l3 4-3 4 M14 5l-4 14",
    "copy": "M8 7h12v14H8z M16 3H4v14",
    "export": "M12 15V3 M7 8l5-5 5 5 M4 13v7h16v-7",
}


def tool_icon(name, color="#20221e"):
    path = _GLYPHS[name]
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="{path}" fill="none" stroke="{color}" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    pixmap = QPixmap(QSize(48, 48))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(svg.encode()).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def paper_section(title, hint, body, *controls):
    section = QWidget()
    layout = QVBoxLayout(section)
    layout.setContentsMargins(0, 3, 0, 3)
    layout.setSpacing(7)
    heading = QHBoxLayout()
    heading.setSpacing(10)
    title.setObjectName("sectionTitle")
    heading.addWidget(title)
    hint.setObjectName("muted")
    hint.setWordWrap(True)
    heading.addWidget(hint, 1)
    for widget in controls:
        heading.addWidget(widget)
    layout.addLayout(heading)
    layout.addWidget(body, 1)
    return section


_STYLE = Template("""
QWidget { font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; color: $ink; }
QMainWindow, QDialog { background: $shell; }
QWidget#navPaper { background: $rail; border: 1px solid $line; }
QWidget#readingPaper { background: $paper; border: 1px solid $line; }
QLabel#title { font-family: 'Segoe UI'; font-size: 25px; font-weight: 700; color: $ink; }
QLabel#muted, QLabel#model { color: $muted; font-size: 12px; }
QLabel#sectionTitle { font-size: 15px; font-weight: 700; border-left: 2px solid $ink; padding-left: 8px; }
QLabel#imprint { font: 11px 'Consolas'; color: $subtleInk; background: $shell; padding: 4px 6px; }
QFrame#rule { background: $line; border: 0; }
QPushButton { background: $button; border: 1px solid $line; border-radius: 0; padding: 6px 12px; min-height: 19px; }
QPushButton:hover { background: $over; border-color: $edge; }
QPushButton:pressed { background: $down; border-color: $edge; padding-top: 7px; padding-bottom: 5px; }
QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus { border-color: $focus; }
QPushButton#quietAction { background: transparent; border-color: transparent; color: $subtleInk; }
QPushButton#quietAction:hover { background: $over; border-color: $line; }
QPushButton#quietAction:pressed { background: $down; border-color: $edge; }
QPushButton#navAction { background: transparent; border: 1px solid transparent; text-align: left; font-weight: 500; padding: 7px 9px; }
QPushButton#navAction:hover { background: $over; border-color: $hairline; }
QPushButton#navAction:pressed { background: $down; border-color: $edge; padding-top: 8px; padding-bottom: 6px; }
QPushButton#primary { background: #fff500; color: #101110; border-color: #ded500; font-weight: 700; padding: 8px 16px; }
QPushButton#primary:hover { background: #fff83e; border-color: #777400; }
QPushButton#primary:pressed { background: #e3d900; border-color: #595800; padding-top: 9px; padding-bottom: 7px; }
QPushButton#recognize { background: $strong; color: #fafbf6; border-color: $strong; }
QPushButton#recognize:hover { background: $strongOver; border-color: $strongOver; }
QPushButton#recognize:pressed { background: $strongDown; border-color: $strongDown; }
QPushButton#navAction:focus, QPushButton#quietAction:focus, QPushButton#primary:focus { border-color: $focus; }
QPushButton#recognize:focus { border-color: #a9a34a; }
QPushButton:disabled, QPushButton#navAction:disabled, QPushButton#recognize:disabled,
QPushButton#quietAction:disabled, QPushButton#primary:disabled { color: $dim; background: $disabled; border-color: $hairline; }
QTabBar::tab { background: $tab; border: 1px solid $line; padding: 8px 12px; color: $subtleInk; min-width: 62px; font-weight: 600; }
QTabBar::tab:!selected:hover { background: $over; border-color: $edge; color: $subtleInk; }
QTabBar::tab:selected { background: #fff500; border-color: #ded500; color: #101110; }
QTabBar::tab:selected:hover { background: #fff83e; border-color: #8c8900; }
QTabBar::tab:pressed { background: $down; border-color: $edge; }
QTabBar::tab:selected:pressed { background: #e3d900; border-color: #706b00; }
QTabBar:disabled::tab { background: $disabled; color: $dim; border-color: $hairline; }
QScrollArea#dropZone { background: $sheet; border: 1px solid $hairline; }
QWidget#dropZone QLabel { background: $sheet; color: $muted; }
QFrame#previewFrame { background: $sheet; border: 1px solid $hairline; }
QPlainTextEdit { background: $sheet; border: 1px solid $hairline; padding: 9px; font: 15px 'Consolas', 'Microsoft YaHei UI'; selection-background-color: #fff500; selection-color: #101110; }
QLineEdit, QKeySequenceEdit { background: $sheet; border: 1px solid $line; padding: 6px 9px; }
QComboBox { combobox-popup: 0; background: $sheet; border: 1px solid $line; border-bottom: 2px solid $line;
            padding: 5px 30px 5px 10px; min-height: 20px; min-width: 84px; font-weight: 600; }
QComboBox:hover { background: $hoverField; border-color: $edge; border-bottom-color: $edge; }
QComboBox:focus { border-color: $focus; border-bottom-color: $focus; }
QComboBox:on { background: $openField; border-color: $edge; border-bottom-color: #a69e00; }
QComboBox:disabled { color: $dim; background: $disabled; border-color: $hairline; }
QComboBox::drop-down { subcontrol-origin: border; subcontrol-position: center right; width: 28px; border: 0; background: transparent; }
QComboBox::down-arrow { image: url("$chevronDown"); width: 14px; height: 14px; }
QComboBox::down-arrow:on { image: url("$chevronUp"); }
QListView#optionList { background: $sheet; border: 1px solid $line; padding: 3px; outline: none; }
QSplitter::handle:vertical { background: $paper; border-top: 1px solid $hairline; }
QSplitter::handle:vertical:hover { background: $over; }
QProgressBar { border: none; background: $track; }
QProgressBar::chunk { background: #c8be00; }
QCheckBox#nightSwitch { color: $ink; padding: 5px 6px; spacing: 10px; border: 1px solid transparent; }
QCheckBox#nightSwitch:hover { background: $over; }
QCheckBox#nightSwitch:focus { border-color: $focus; }
QCheckBox#nightSwitch::indicator { width: 28px; height: 16px; }
QCheckBox#nightSwitch::indicator:unchecked { image: url("$switchOff"); }
QCheckBox#nightSwitch::indicator:checked { image: url("$switchOn"); }
QToolTip { background: $paper; color: $ink; border: 1px solid $line; }
""")


def stylesheet(night):
    suffix = "-night" if night else ""
    return _STYLE.substitute(theme_colors(night),
                             chevronDown=(ASSETS / f"chevron-down{suffix}.svg").as_posix(),
                             chevronUp=(ASSETS / f"chevron-up{suffix}.svg").as_posix(),
                             switchOff=(ASSETS / "switch-off.svg").as_posix(),
                             switchOn=(ASSETS / "switch-on.svg").as_posix())


STYLE = stylesheet(False)
