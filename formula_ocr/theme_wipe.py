"""Reveal the new theme from the bottom-left corner of the workspace."""
from PySide6.QtCore import QEvent, QEasingCurve, QPoint, QPointF, QRect, Qt, QVariantAnimation
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QStyle, QWidget


class ThemeWipe(QWidget):
    def __init__(self, surface):
        # A transparent owned window also covers the native WebView2 child.
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
                 | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(surface.window(), flags)
        self.surface = surface
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.snapshot = QPixmap()
        self.motion = QVariantAnimation(self)
        self.motion.setDuration(460)
        self.motion.setStartValue(0.0)
        self.motion.setEndValue(1.0)
        self.motion.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.motion.valueChanged.connect(lambda _: self.update())
        self.motion.finished.connect(self.stop)
        surface.window().installEventFilter(self)

    def can_animate(self):
        return (self.surface.isVisible() and not self.surface.window().isMinimized()
                and QApplication.activeModalWidget() is None
                and self.style().styleHint(QStyle.StyleHint.SH_Widget_Animate))

    def cover(self, preview, native_frame):
        self.snapshot = self.surface.grab()
        if self.snapshot.isNull():
            return
        if native_frame is not None:
            painter = QPainter(self.snapshot)
            area = QRect(preview.mapTo(self.surface, QPoint()), preview.size())
            painter.drawPixmap(area, native_frame, native_frame.rect())
            painter.end()
        self.motion.setCurrentTime(0)
        self.setGeometry(QRect(self.surface.mapToGlobal(QPoint()), self.surface.size()))
        self.show()
        self.raise_()

    def play(self):
        if self.isVisible():
            self.motion.start()

    def stop(self):
        self.motion.stop()
        self.hide()
        self.snapshot = QPixmap()

    def eventFilter(self, obj, event):
        if self.isVisible() and event.type() in (QEvent.Type.Hide, QEvent.Type.Resize, QEvent.Type.Move,
                                                QEvent.Type.DevicePixelRatioChange):
            self.stop()
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        if self.snapshot.isNull():
            return
        w, h = self.width(), self.height()
        edge = (w + h) * self.motion.currentValue()
        # The top and bottom intersections of the same 45-degree line.
        # Only the outgoing side is painted. The revealed side is the live UI.
        outgoing = QPainterPath()
        outgoing.moveTo(edge - h, 0)
        outgoing.lineTo(w + h, 0)
        outgoing.lineTo(w + h, h)
        outgoing.lineTo(edge, h)
        outgoing.closeSubpath()
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipPath(outgoing)
        painter.drawPixmap(QPointF(), self.snapshot)
