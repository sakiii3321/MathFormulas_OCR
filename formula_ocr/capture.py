"""Frozen per-monitor region selection; crops use physical image pixels."""
import math

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget


def crop_selection(image, selection, logical_size):
    rect = QRectF(selection).normalized().intersected(QRectF(QPointF(), logical_size))
    if rect.width() < 4 or rect.height() < 4:
        return QImage()
    sx, sy = image.width() / logical_size.width(), image.height() / logical_size.height()
    x, y = math.floor(rect.left() * sx), math.floor(rect.top() * sy)
    right, bottom = math.ceil(rect.right() * sx), math.ceil(rect.bottom() * sy)
    result = image.copy(QRect(x, y, right - x, bottom - y))
    result.setDevicePixelRatio(1.0)
    return result


class SelectionOverlay(QWidget):
    selected = Signal(QImage)
    cancelled = Signal()

    def __init__(self, screen, snapshot):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.snapshot = snapshot
        self.origin = None
        self.selection = QRectF()
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.snapshot)
        shade = QPainterPath()
        shade.addRect(QRectF(self.rect()))
        if not self.selection.isEmpty():
            shade.addRect(self.selection)
        painter.fillPath(shade, QColor(0, 0, 0, 110))
        painter.setPen(QPen(QColor("#4da3ff"), 2))
        if not self.selection.isEmpty():
            painter.drawRect(self.selection)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(24, 34, "拖动框选公式，松开后识别 · Esc / 右键取消 · 每次选择一个屏幕内的区域")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position()
            self.selection = QRectF()
            self.update()

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.selection = QRectF(self.origin, event.position()).normalized().intersected(QRectF(self.rect()))
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.origin is not None:
            rect = QRectF(self.origin, event.position())
            self.origin = None
            image = crop_selection(self.snapshot.toImage(), rect, self.size().toSizeF())
            if image.isNull():
                self.cancelled.emit()
            else:
                self.selected.emit(image)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)


class ScreenCapture(QObject):
    completed = Signal(QImage)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overlays = []

    def start(self):
        try:
            # Capture every monitor before showing any overlay.
            snapshots = [(screen, screen.grabWindow(0)) for screen in QApplication.screens()]
            if not snapshots or any(pixmap.isNull() for _, pixmap in snapshots):
                raise ValueError("无法获取屏幕图像，请检查桌面或远程会话是否可截图。")
            for screen, snapshot in snapshots:
                overlay = SelectionOverlay(screen, snapshot)
                overlay.selected.connect(self.finish)
                overlay.cancelled.connect(self.cancel)
                self.overlays.append(overlay)
            for overlay in self.overlays:
                overlay.show()
            target = next((item for item in self.overlays if item.geometry().contains(QCursor.pos())), self.overlays[0])
            target.activateWindow()
            target.setFocus()
        except Exception as exc:
            self.clear()
            self.failed.emit(str(exc))

    def clear(self):
        for overlay in self.overlays:
            overlay.close()
            overlay.deleteLater()
        self.overlays.clear()

    def finish(self, image):
        self.clear()
        self.completed.emit(image)

    def cancel(self):
        self.clear()
        self.cancelled.emit()
