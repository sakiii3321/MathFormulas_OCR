import html
import sys
from pathlib import Path

import keyring
from PySide6.QtCore import QBuffer, QIODevice, QSettings, QTemporaryDir, QUrl, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QKeySequenceEdit, QPlainTextEdit, QProgressBar, QScrollArea, QSizePolicy, QSplitter, QTabBar, QVBoxLayout, QWidget)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings

from .core import endpoint, export_text, mathml, recognize
from .capture import ScreenCapture
from .clipboard import CODE_FORMATS, COPY_FORMATS, WORD_FORMAT, copy_formula, copy_mixed
from .hotkey import DEFAULT_HOTKEY, GlobalHotkey
from .providers import PROVIDERS
from .theme import (ASSETS, STYLE, ActionButton, FieldSelect, apply_theme, field_map,
                    paper_section, preview_css, theme_colors, tool_icon)
from .mixed import (MIXED_FORMATS, MIXED_COPY_FORMATS, MIXED_WORD, MIXED_EXAMPLE,
                    from_markdown, to_markdown, to_html, recognize_mixed, save_document)

SERVICE = "FormulaOCR"
EXAMPLE = r"\max_i \frac{\left|T_{\mathrm{sim},i}-T_{\mathrm{exp},i}\right|}{T_{\mathrm{sim},i}}\times 100\%"


def settings_actions(dialog):
    actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    save = actions.button(QDialogButtonBox.StandardButton.Save)
    save.setText("保存")
    save.setObjectName("primary")
    actions.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
    for button in actions.buttons():
        button.setCursor(Qt.CursorShape.PointingHandCursor)
    actions.accepted.connect(dialog.save)
    actions.rejected.connect(dialog.reject)
    return actions


class Worker(QThread):
    result = Signal(object)
    error = Signal(str)

    def __init__(self, args, parent, mode="formula"):
        super().__init__(parent)
        self.args = args
        self.mode = mode

    def run(self):
        try:
            self.result.emit(recognize_mixed(*self.args) if self.mode == "mixed" else recognize(*self.args))
        except Exception as exc:
            self.error.emit(str(exc) if isinstance(exc, ValueError) else "识别失败，请检查接口配置后重试。")


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("API 设置")
        self.setMinimumWidth(540)
        form = QFormLayout(self)
        form.setContentsMargins(22, 18, 22, 18)
        form.setVerticalSpacing(10)
        self.provider = FieldSelect()
        self.provider.addItems(list(PROVIDERS))
        self.provider.setCurrentText(parent.settings.value("provider", "自定义兼容接口"))
        form.addRow("API 来源", self.provider)
        self.base = QLineEdit(parent.settings.value("base", "https://api.openai.com/v1"))
        self.model = QLineEdit(parent.settings.value("model", ""))
        self.model.setPlaceholderText("填写服务商提供的视觉模型 ID")
        self.key = QLineEdit(parent.api_key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("本地免鉴权服务可留空")
        self.remember = QCheckBox("将 API Key 保存到 Windows 凭据管理器")
        self.remember.setChecked(parent.settings.value("remember", False, type=bool))
        self.hint = QLabel(PROVIDERS[self.provider.currentText()][2])
        self.hint.setWordWrap(True)
        form.addRow(self.hint)
        form.addRow("Base URL", self.base)
        form.addRow("模型名称", self.model)
        form.addRow("API Key", self.key)
        form.addRow(self.remember)
        note = QLabel("支持 OpenAI 兼容的 Chat Completions 图像接口。\n点击识别时，图片会发送到上面的地址，费用由服务商计收。\n请使用支持图像输入的模型；纯文本模型无法识别图片。")
        note.setWordWrap(True)
        form.addRow(note)
        form.addRow(settings_actions(self))
        self.provider.currentTextChanged.connect(self.change_provider)
        self.base.textEdited.connect(lambda: self.key.clear())

    def change_provider(self, name):
        parent = self.parent()
        base, model, hint = PROVIDERS[name]
        prefix = "profiles/" + name + "/"
        base = parent.settings.value(prefix + "base", base)
        self.base.setText(base)
        self.model.setText(parent.settings.value(prefix + "model", model))
        self.hint.setText(hint)
        remember = parent.settings.value(prefix + "remember", False, type=bool)
        self.remember.setChecked(remember)
        key = parent.session_keys.get(base, "")
        if remember:
            try:
                key = keyring.get_password(SERVICE, base) or key
            except Exception:
                self.hint.setText(hint + " 无法读取凭据，请重新输入密钥。")
        self.key.setText(key)

    def save(self):
        parent = self.parent()
        try:
            endpoint(self.base.text())
            if not self.model.text().strip():
                raise ValueError("请填写模型名称。")
            # Bind stored credentials to the destination to avoid sending a previous key to a new host.
            account = self.base.text().strip().rstrip("/")
            prefix = "profiles/" + self.provider.currentText() + "/"
            if self.remember.isChecked() and self.key.text().strip():
                keyring.set_password(SERVICE, account, self.key.text().strip())
            elif parent.settings.value(prefix + "remember", False, type=bool) and keyring.get_password(SERVICE, account):
                keyring.delete_password(SERVICE, account)
        except Exception as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return
        parent.settings.setValue("base", account)
        parent.settings.setValue("model", self.model.text().strip())
        parent.settings.setValue("remember", self.remember.isChecked())
        parent.settings.setValue("provider", self.provider.currentText())
        parent.settings.setValue(prefix + "base", account)
        parent.settings.setValue(prefix + "model", self.model.text().strip())
        parent.settings.setValue(prefix + "remember", self.remember.isChecked())
        parent.api_key = self.key.text().strip()
        parent.session_keys[account] = parent.api_key
        parent.update_model_label()
        self.accept()


class PreferencesDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("使用设置")
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        form.setContentsMargins(22, 18, 22, 18)
        form.setVerticalSpacing(10)
        self.hotkey = QKeySequenceEdit(QKeySequence(parent.settings.value("capture/hotkey", DEFAULT_HOTKEY)))
        self.hotkey.setMaximumSequenceLength(1)
        form.addRow("全局截图快捷键", self.hotkey)
        help_text = QLabel("点击输入框后按下新组合键，须包含 Ctrl 或 Alt。\n程序运行或最小化时有效；截图后会自动调用 API 识别。\n按 Esc 或右键取消截图，不会发送图片。")
        help_text.setWordWrap(True)
        form.addRow(help_text)
        self.auto_copy = QCheckBox("识别成功后自动复制")
        self.auto_copy.setChecked(parent.settings.value("copy/enabled", False, type=bool))
        form.addRow(self.auto_copy)
        self.copy_format = FieldSelect()
        self.copy_format.addItems(COPY_FORMATS)
        self.copy_format.setCurrentText(parent.settings.value("copy/format", "LaTeX"))
        self.copy_format.setEnabled(self.auto_copy.isChecked())
        self.auto_copy.toggled.connect(self.copy_format.setEnabled)
        form.addRow("自动复制格式", self.copy_format)
        self.mixed_auto_copy = QCheckBox("混合模式：识别成功后自动复制")
        self.mixed_auto_copy.setChecked(parent.settings.value("mixed_copy/enabled", False, type=bool))
        form.addRow(self.mixed_auto_copy)
        self.mixed_copy_format = FieldSelect()
        self.mixed_copy_format.addItems(MIXED_COPY_FORMATS)
        self.mixed_copy_format.setCurrentText(parent.settings.value("mixed_copy/format", "Markdown"))
        self.mixed_copy_format.setEnabled(self.mixed_auto_copy.isChecked())
        self.mixed_auto_copy.toggled.connect(self.mixed_copy_format.setEnabled)
        form.addRow("混合模式复制格式", self.mixed_copy_format)
        self.auto_copy.setText("公式模式：识别成功后自动复制")
        note = QLabel("MathML 是源码；Word 公式包含可供 Word 导入的剪贴板格式。\n自动复制会替换剪贴板内容；手动编辑公式不会触发自动复制。")
        note.setWordWrap(True)
        form.addRow(note)
        form.addRow(settings_actions(self))

    def save(self):
        parent = self.parent()
        try:
            sequence = parent.hotkey.register(self.hotkey.keySequence().toString(QKeySequence.SequenceFormat.PortableText))
        except ValueError as exc:
            QMessageBox.warning(self, "快捷键无法使用", str(exc))
            return
        parent.settings.setValue("capture/hotkey", sequence)
        parent.settings.setValue("copy/enabled", self.auto_copy.isChecked())
        parent.settings.setValue("copy/format", self.copy_format.currentText())
        parent.settings.setValue("mixed_copy/enabled", self.mixed_auto_copy.isChecked())
        parent.settings.setValue("mixed_copy/format", self.mixed_copy_format.currentText())
        parent.update_capture_hint()
        parent.status.setText("使用设置已保存。")
        self.accept()


class ImagePane(QScrollArea):
    file_dropped = Signal(str)
    image_dropped = Signal(QImage)

    def __init__(self):
        super().__init__()
        self.original = QPixmap()
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidget(self.canvas)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)
        self.setMinimumHeight(76)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setObjectName("dropZone")
        self.show_hint(False)

    def show_hint(self, mixed):
        if self.original.isNull():
            kind = "图文截图" if mixed else "公式图片"
            self.canvas.setText(f"将{kind}拖到这里，或按 Ctrl+V 粘贴\nPNG / JPG / BMP / WebP   ·   最大 10 MB")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls() and mime.urls()[0].isLocalFile():
            self.file_dropped.emit(mime.urls()[0].toLocalFile())
        elif mime.hasImage():
            self.image_dropped.emit(QImage(mime.imageData()))
        event.acceptProposedAction()

    def show_image(self, image):
        self.original = QPixmap.fromImage(image)
        self.refresh()
        self.verticalScrollBar().setValue(0)

    def refresh(self):
        viewport = self.viewport().size()
        if self.original.isNull():
            self.canvas.resize(viewport)
            return
        scale = self.devicePixelRatioF()
        width = min(max(1, round((viewport.width() - 8) * scale)), self.original.width())
        shown = self.original.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
        shown.setDevicePixelRatio(scale)
        self.canvas.resize(viewport.width(), max(viewport.height(), round(shown.height() / scale) + 8))
        self.canvas.setPixmap(shown)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()


class Window(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.setWindowTitle("Formula OCR · AI 公式识别")
        self.setWindowIcon(QIcon(str(ASSETS / "formula-ocr.ico")))
        available = self.screen().availableGeometry()
        self.resize(min(1200, available.width() - 24), min(840, available.height() - 56))
        self.settings = settings if settings is not None else QSettings("FormulaOCR", "Desktop")
        self.api_key = ""
        self.credential_error = False
        if self.settings.value("remember", False, type=bool):
            try:
                self.api_key = keyring.get_password(SERVICE, self.settings.value("base", "https://api.openai.com/v1")) or ""
            except Exception:
                self.credential_error = True
        self.png = None
        self.session_keys = {self.settings.value("base", "https://api.openai.com/v1"): self.api_key}
        self.worker = None
        self.active_mode = "formula"
        self.mode_drafts = {"formula": "", "mixed": ""}
        self.mixed_assets = {}
        self.preview_temp = None
        self.closing = False
        self.capturing = False
        self.capture = ScreenCapture(self)
        self.capture.completed.connect(self.capture_completed)
        self.capture.cancelled.connect(self.capture_cancelled)
        self.capture.failed.connect(self.capture_failed)
        self.hotkey = GlobalHotkey(self.start_capture)
        QApplication.instance().aboutToQuit.connect(self.hotkey.close)
        self.terrain = QSvgWidget()
        self.setCentralWidget(self.terrain)
        columns = QHBoxLayout(self.terrain)
        columns.setContentsMargins(14, 32, 14, 14)
        columns.setSpacing(0)

        rail = QWidget()
        rail.setFixedWidth(228)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(0, 0, 0, 0)
        nav = QWidget()
        nav.setObjectName("navPaper")
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(14, 16, 14, 12)
        nav_layout.setSpacing(8)
        brand = QHBoxLayout()
        brand.setSpacing(7)
        logo = QLabel()
        logo.setFixedSize(37, 37)
        logo.setPixmap(QIcon(str(ASSETS / "formula-ocr.svg")).pixmap(logo.size(), self.devicePixelRatioF()))
        brand.addWidget(logo)
        title = QLabel("Formula OCR")
        title.setObjectName("title")
        brand.addWidget(title, 1)
        nav_layout.addLayout(brand)
        subtitle = QLabel("公式识别与图文转录")
        subtitle.setObjectName("muted")
        nav_layout.addWidget(subtitle)
        rule = QFrame()
        rule.setObjectName("rule")
        rule.setFixedHeight(1)
        nav_layout.addWidget(rule)
        self.mode = QTabBar()
        self.mode.setAccessibleName("识别模式")
        self.mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode.setExpanding(True)
        self.mode.addTab("公式模式")
        self.mode.addTab("混合模式")
        self.mode.setTabData(0, "formula")
        self.mode.setTabData(1, "mixed")
        nav_layout.addWidget(self.mode)
        nav_layout.addSpacing(6)
        self.capture_button = self.button("截图识别", self.start_capture)
        self.import_button = self.button("导入图片", self.open_file)
        self.paste_button = self.button("粘贴截图", self.paste_image)
        self.settings_button = self.button("API 设置", self.open_settings)
        self.preferences_button = self.button("使用设置", self.open_preferences)
        self.icon_buttons = [(self.capture_button, "capture"), (self.import_button, "image"),
                             (self.paste_button, "paste"), (self.settings_button, "api"),
                             (self.preferences_button, "settings")]
        for button, _ in self.icon_buttons:
            button.setObjectName("navAction")
            nav_layout.addWidget(button)
        shortcut_layout = QHBoxLayout(self.capture_button)
        shortcut_layout.setContentsMargins(0, 0, 5, 0)
        shortcut_layout.addStretch()
        self.shortcut_label = QLabel()
        self.shortcut_label.setObjectName("muted")
        self.shortcut_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        shortcut_layout.addWidget(self.shortcut_label)
        self.model_label = QLabel()
        self.model_label.setObjectName("model")
        self.model_label.setWordWrap(True)
        self.model_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        nav_layout.addWidget(self.model_label)
        self.night_switch = QCheckBox("夜间模式")
        self.night_switch.setObjectName("nightSwitch")
        self.night_switch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.night_switch.setChecked(self.settings.value("appearance/night", False, type=bool))
        nav_layout.addWidget(self.night_switch)
        rail_layout.addWidget(nav)
        rail_layout.addStretch()
        imprint = QLabel("FIELD MANUAL\nREADING DESK")
        imprint.setObjectName("imprint")
        rail_layout.addWidget(imprint, 0, Qt.AlignmentFlag.AlignLeft)
        columns.addWidget(rail)

        paper = QWidget()
        paper.setObjectName("readingPaper")
        columns.addWidget(paper, 1)
        layout = QVBoxLayout(paper)
        layout.setContentsMargins(20, 13, 20, 12)
        layout.setSpacing(8)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(7)
        layout.addWidget(splitter, 1)

        self.drop = ImagePane()
        self.drop.file_dropped.connect(self.load_file)
        self.drop.image_dropped.connect(self.load_image)
        self.run_button = self.button("识别公式", self.start_recognition)
        self.run_button.setObjectName("recognize")
        self.example_button = self.button("查看示例", self.show_example)
        self.example_button.setObjectName("quietAction")
        splitter.addWidget(paper_section(QLabel("原图"), QLabel("截图、粘贴或导入图片"), self.drop,
                                         self.example_button, self.run_button))

        self.preview = QWebEngineView()
        self.preview.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, False)
        self.preview.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        preview_frame = QFrame()
        preview_frame.setObjectName("previewFrame")
        preview_frame.setMinimumHeight(76)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(1, 1, 1, 1)
        preview_layout.addWidget(self.preview)
        self.preview_label = QLabel("公式预览")
        self.mode_hint = QLabel("识别后的数学公式")
        splitter.addWidget(paper_section(self.preview_label, self.mode_hint, preview_frame))

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("识别结果会出现在这里，也可以直接输入 LaTeX…")
        self.editor.setMinimumHeight(72)
        self.editor_label = QLabel("编辑")
        self.format = FieldSelect()
        self.format.setAccessibleName("输出格式")
        self.format.addItems(CODE_FORMATS)
        format_label = QLabel("输出格式")
        format_label.setObjectName("muted")
        format_label.setBuddy(self.format)
        copy_code = self.button("复制代码", self.copy_code)
        copy_code.setObjectName("quietAction")
        export_file = self.button("导出文件", self.save_file)
        export_file.setObjectName("quietAction")
        splitter.addWidget(paper_section(self.editor_label, QLabel("修改源码即可更新预览"), self.editor,
                                         format_label, self.format, copy_code, export_file))
        splitter.setSizes([208, 280, 185])

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        layout.addWidget(self.progress)
        output = QHBoxLayout()
        self.status = QLabel("准备就绪。导入图片后点击识别。")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        output.addWidget(self.status, 1)
        copy_word = self.button("复制到 Word", self.copy_word)
        copy_word.setObjectName("primary")
        output.addWidget(copy_word)
        self.docx_button = self.button("导出 DOCX", self.save_docx)
        self.icon_buttons.extend([(copy_code, "copy"), (export_file, "export"),
                                  (copy_word, "copy"), (self.docx_button, "export")])
        self.docx_button.hide()
        output.addWidget(self.docx_button)
        layout.addLayout(output)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.render)
        self.editor.textChanged.connect(lambda: self.timer.start())
        # Only intercept paste when the clipboard contains an image; text paste remains native.
        QApplication.instance().installEventFilter(self)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_file)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.start_recognition)
        self.update_model_label()
        self.apply_appearance(self.night_switch.isChecked())
        self.night_switch.toggled.connect(self.change_appearance)
        if self.credential_error:
            self.status.setText("无法读取已保存的密钥，请在 API 设置中重新输入。")
        try:
            self.hotkey.register(self.settings.value("capture/hotkey", DEFAULT_HOTKEY))
        except ValueError as exc:
            self.status.setText(str(exc) + " 可在「使用设置」中更换，或点击「截图识别」。")
        self.update_capture_hint()
        self.mode.currentChanged.connect(self.change_mode)
        if self.settings.value("recognition/mode", "formula") == "mixed":
            self.mode.setCurrentIndex(1)

    @staticmethod
    def button(text, callback):
        result = ActionButton(text)
        result.clicked.connect(callback)
        return result

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if self.isActiveWindow() and event.type() == QEvent.Type.KeyPress and event.matches(QKeySequence.StandardKey.Paste):
            if QApplication.clipboard().mimeData().hasImage():
                self.paste_image()
                return True
        return super().eventFilter(obj, event)

    def update_model_label(self):
        model = self.settings.value("model", "")
        self.model_label.setText(self.settings.value("provider", "自定义") + " · " + model if model else "尚未配置模型")

    def open_settings(self):
        SettingsDialog(self).exec()

    def open_preferences(self):
        PreferencesDialog(self).exec()

    def apply_appearance(self, night):
        apply_theme(QApplication.instance(), night)
        self.terrain.load(field_map(night))
        colors = theme_colors(night)
        for button, glyph in self.icon_buttons:
            ink = "#20221e" if button.objectName() == "primary" else colors["ink"]
            button.setIcon(tool_icon(glyph, ink))
        self.preview.page().setBackgroundColor(QColor(colors["sheet"]))
        self.render()

    def change_appearance(self, night):
        self.apply_appearance(night)
        self.settings.setValue("appearance/night", night)

    def change_mode(self):
        self.mode_drafts[self.active_mode] = self.editor.toPlainText()
        self.active_mode = self.mode.tabData(self.mode.currentIndex())
        mixed = self.active_mode == "mixed"
        self.settings.setValue("recognition/mode", self.active_mode)
        self.format.clear()
        self.format.addItems(MIXED_FORMATS if mixed else CODE_FORMATS)
        self.docx_button.setVisible(mixed)
        self.run_button.setText("识别图文" if mixed else "识别公式")
        self.preview_label.setText("图文预览" if mixed else "公式预览")
        self.mode_hint.setText("正文、公式与原始编号" if mixed else "识别后的数学公式")
        self.editor.setPlaceholderText("输入正文，行内公式用 $…$；独立公式的前后 $$ 各占一行。空行分段。" if mixed else "识别结果会出现在这里，也可以直接输入 LaTeX…")
        self.editor.setPlainText(self.mode_drafts[self.active_mode])
        self.drop.show_hint(mixed)
        self.status.setText("已切换到" + ("混合模式。保留原文与编号，不自动翻译或改写。" if mixed else "公式模式。"))
        self.render()

    def show_example(self):
        self.editor.setPlainText(MIXED_EXAMPLE if self.active_mode == "mixed" else EXAMPLE)

    def mixed_document(self):
        return from_markdown(self.editor.toPlainText(), self.mixed_assets)

    def update_capture_hint(self):
        shortcut = self.hotkey.sequence if self.hotkey.id is not None else "快捷键未启用"
        self.capture_button.setToolTip(f"{shortcut}：框选后自动识别；Esc / 右键取消")
        self.shortcut_label.setText(shortcut if self.hotkey.id is not None else "")

    def start_capture(self):
        if self.capturing or self.closing or QApplication.activeModalWidget() is not None:
            return
        if self.worker and self.worker.isRunning():
            self.status.setText("当前正在识别，请完成后再截图。")
            return
        self.capturing = True
        self.capture_window_state = self.windowState()
        self.capture_quit_policy = QApplication.instance().quitOnLastWindowClosed()
        QApplication.instance().setQuitOnLastWindowClosed(False)
        self.hide()
        # Let Windows repaint the desktop after hiding our own window.
        QTimer.singleShot(220, self.capture.start)

    def restore_after_capture(self, cancelled=False):
        self.capturing = False
        state = self.capture_window_state
        if not cancelled:
            state &= ~Qt.WindowState.WindowMinimized
        self.setWindowState(state)
        self.show()
        if not cancelled:
            self.raise_()
            self.activateWindow()
        QApplication.instance().setQuitOnLastWindowClosed(self.capture_quit_policy)

    def capture_completed(self, image):
        self.restore_after_capture()
        if self.load_image(image):
            self.start_recognition()

    def capture_cancelled(self):
        self.restore_after_capture(cancelled=True)
        self.status.setText("已取消截图。")

    def capture_failed(self, message):
        self.restore_after_capture()
        self.error("截图失败：" + message)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择公式图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.load_file(path)

    def load_file(self, path):
        from pathlib import Path
        try:
            if Path(path).stat().st_size > 10 * 1024 * 1024:
                raise ValueError("图片文件不能超过 10 MB。")
            self.load_image(QImage(path))
        except (OSError, ValueError) as exc:
            self.error(str(exc))

    def load_image(self, image):
        if self.worker and self.worker.isRunning():
            return False
        if image.isNull():
            self.error("无法读取图片，请使用 PNG、JPG、BMP 或 WebP。")
            return False
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        data = bytes(buffer.data())
        if len(data) > 10 * 1024 * 1024:
            self.error("图片转为 PNG 后超过 10 MB，请先裁剪公式区域。")
            return False
        self.png = data
        self.mode_drafts = {"formula": "", "mixed": ""}
        self.mixed_assets = {}
        self.drop.show_image(image)
        self.editor.clear()
        self.status.setText(f"图片已载入（{image.width()} × {image.height()}）。点击识别后发送到配置的 API。")
        return True

    def paste_image(self):
        mime = QApplication.clipboard().mimeData()
        if mime.hasImage():
            self.load_image(QApplication.clipboard().image())
        elif mime.hasUrls() and mime.urls()[0].isLocalFile():
            self.load_file(mime.urls()[0].toLocalFile())
        else:
            self.error("剪贴板中没有图片。可用 Win+Shift+S 截取公式后粘贴。")

    def start_recognition(self):
        if self.worker and self.worker.isRunning():
            return
        if self.png is None:
            self.error("请先导入或粘贴一张公式图片。")
            return
        if not self.settings.value("model", ""):
            self.open_settings()
            if not self.settings.value("model", ""):
                return
        self.set_busy(True)
        self.status.setText("正在识别图文结构… 请稍候。" if self.active_mode == "mixed" else "正在识别公式… 请稍候。")
        self.worker = Worker((self.png, self.settings.value("base"), self.api_key, self.settings.value("model")), self, self.active_mode)
        self.worker.result.connect(self.got_result)
        self.worker.error.connect(self.error)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def set_busy(self, busy):
        for widget in [self.mode, self.run_button, self.capture_button, self.import_button, self.paste_button, self.settings_button, self.preferences_button, self.example_button, self.editor]:
            widget.setEnabled(not busy)
        self.progress.setVisible(busy)

    def got_result(self, text):
        if self.active_mode == "mixed":
            self.mixed_assets = text.assets
            self.editor.setPlainText(to_markdown(text))
            if self.settings.value("mixed_copy/enabled", False, type=bool):
                kind = self.settings.value("mixed_copy/format", "Markdown")
                try:
                    copy_mixed(text, kind)
                    self.status.setText(f"图文识别完成，已自动复制 {kind}。请核对文字、公式、编号和插图范围。")
                except Exception as exc:
                    self.error("图文识别完成，但自动复制失败：" + str(exc))
            else:
                self.status.setText("图文识别完成。请核对文字、公式、编号和插图范围，再复制或导出。")
            return
        self.editor.setPlainText(text)
        if self.settings.value("copy/enabled", False, type=bool):
            kind = self.settings.value("copy/format", "LaTeX")
            try:
                copy_formula(text, kind)
                self.status.setText(f"识别完成，已自动复制 {kind}。请核对公式后使用。")
            except Exception:
                self.status.setText("识别完成，但自动复制失败；原剪贴板未替换。请检查公式或更换复制格式。")
        else:
            self.status.setText("识别完成。请对照原图检查符号、上下标和矩阵结构，再复制或导出。")

    def finished(self):
        self.set_busy(False)
        if self.closing:
            self.close()

    def error(self, message):
        self.status.setText(message)

    def render(self):
        text = self.editor.toPlainText().strip()
        css = preview_css(self.night_switch.isChecked())
        if self.active_mode == "mixed" and text:
            try:
                markup = to_html(self.mixed_document(), preview=True)
                markup = markup.replace("</style>", css + "</style>", 1)
                if len(markup.encode('utf-8')) < 1_000_000:
                    self.preview.setHtml(markup)
                else:
                    # Qt setHtml has a data-URL size limit; large embedded figures use a local file.
                    from pathlib import Path
                    if self.preview_temp is None:
                        self.preview_temp = QTemporaryDir()
                    if not self.preview_temp.isValid():
                        raise ValueError("无法创建本地图文预览文件。")
                    path = Path(self.preview_temp.path()) / 'preview.html'
                    path.write_text(markup, encoding='utf-8')
                    self.preview.setUrl(QUrl.fromLocalFile(str(path)))
                return
            except Exception as exc:
                body = '<p class="formula-error">' + html.escape(str(exc)) + '</p>'
        elif not text:
            body = '<p class="preview-note">识别或输入内容后，在此查看预览</p>'
        else:
            try:
                body = mathml(text)
            except Exception:
                body = '<p class="formula-error">暂时无法预览，请检查 LaTeX 语法或转换器是否支持该命令。仍可复制 LaTeX。</p>'
        self.preview.setHtml('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><style>body{margin:0;min-height:calc(100vh - 28px);display:flex;align-items:center;justify-content:center}p{font:14px sans-serif}math{font-size:27px;font-family:"Cambria Math",serif}' + css + '</style></head><body>' + body + '</body></html>')

    def copy_code(self):
        try:
            if self.active_mode == "mixed":
                copy_mixed(self.mixed_document(), self.format.currentText())
            else:
                copy_formula(self.editor.toPlainText(), self.format.currentText())
            self.status.setText("已复制 " + self.format.currentText())
        except Exception as exc:
            self.error("无法生成此格式：" + str(exc))

    def copy_word(self):
        try:
            if self.active_mode == "mixed":
                copy_mixed(self.mixed_document(), MIXED_WORD)
                self.status.setText("已复制整段图文，请在 Word 中保留源格式粘贴；插图或公式兼容性不佳时请导出 Word 文档。")
                return
            copy_formula(self.editor.toPlainText(), WORD_FORMAT)
            self.status.setText("已复制 MathML，请在 Word 中粘贴。若显示源码，可改用 LaTeX 并在 Word 的公式区域粘贴。")
        except Exception:
            self.error("无法转换为 MathML，请检查公式内容和 LaTeX 命令。")

    def save_file(self):
        if self.active_mode == "mixed":
            self.save_mixed_file(self.format.currentText())
            return
        try:
            text = export_text(self.editor.toPlainText(), self.format.currentText())
        except Exception:
            self.error("无法导出，请检查公式内容和 LaTeX 语法。")
            return
        is_mathml = self.format.currentText() == "MathML"
        path, _ = QFileDialog.getSaveFileName(self, "导出公式", "formula.mml" if is_mathml else "formula.tex", "MathML (*.mml)" if is_mathml else "LaTeX (*.tex)")
        if path:
            try:
                Path(path).write_text(text, encoding="utf-8")
                self.status.setText("已导出：" + path)
            except OSError as exc:
                self.error("保存失败：" + str(exc))

    def save_docx(self):
        self.save_mixed_file('DOCX')

    def save_mixed_file(self, kind):
        try:
            doc = self.mixed_document()
        except Exception as exc:
            self.error("无法导出：" + str(exc))
            return
        suffix = {'Markdown': 'md', 'LaTeX': 'tex', 'HTML': 'html', 'DOCX': 'docx'}[kind]
        path, _ = QFileDialog.getSaveFileName(self, "导出图文", 'document.' + suffix, f'{kind} (*.{suffix})')
        if path:
            try:
                save_document(doc, path, kind)
                self.status.setText("已导出：" + path)
            except Exception as exc:
                self.error("导出失败：" + str(exc))

    def closeEvent(self, event):
        if self.capturing:
            event.ignore()
            return
        if self.worker and self.worker.isRunning():
            self.closing = True
            self.status.setText("等待当前请求结束后关闭（最长约 135 秒）…")
            event.ignore()
        else:
            self.hotkey.close()
            event.accept()




def main():
    if sys.platform == "win32":
        from ctypes import windll
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("FormulaOCR.Desktop")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = Window()
    window.show()
    sys.exit(app.exec())
