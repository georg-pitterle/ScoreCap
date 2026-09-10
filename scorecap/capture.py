"""Full-screen selection overlay and the screen grab behind it."""

from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .model import Shot

MIN_SELECTION_PX = 20
DIM_COLOR = QColor(0, 0, 0, 110)
BORDER_COLOR = QColor(255, 255, 255)


def normalized_rect(start: QPoint, end: QPoint) -> QRect:
    # QRect(QPoint, QPoint) treats both corners as inclusive, which is one
    # pixel off for a drag; build the rectangle from the coordinates instead.
    left, right = sorted((start.x(), end.x()))
    top, bottom = sorted((start.y(), end.y()))
    return QRect(left, top, right - left, bottom - top)


def is_valid_selection(rect: QRect) -> bool:
    return rect.width() >= MIN_SELECTION_PX and rect.height() >= MIN_SELECTION_PX


def virtual_geometry() -> QRect:
    geometry = QRect()
    for screen in QGuiApplication.screens():
        geometry = geometry.united(screen.geometry())
    return geometry


def grab(rect: QRect, target_dir: Path) -> Shot:
    """Grab a screen region. Qt maps logical coordinates to physical pixels."""
    screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
    pixmap = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"shot-{uuid.uuid4().hex}.png"
    pixmap.save(str(path), "PNG")
    return Shot(path=path, width=pixmap.width(), height=pixmap.height())


class SelectionOverlay(QWidget):
    selected = Signal(QRect)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self._start: QPoint | None = None
        self._current: QPoint | None = None

    def start(self) -> None:
        self._start = None
        self._current = None
        self.setGeometry(virtual_geometry())
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def _selection(self) -> QRect:
        if self._start is None or self._current is None:
            return QRect()
        return normalized_rect(self._start, self._current)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.fillRect(self.rect(), DIM_COLOR)
        selection = self._selection()
        if selection.isNull():
            return
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(selection, Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setPen(QPen(BORDER_COLOR, 1))
        painter.drawRect(selection.adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._start = event.position().toPoint()
            self._current = self._start
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._start is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton or self._start is None:
            return
        selection = self._selection()
        self.hide()
        if is_valid_selection(selection):
            self.selected.emit(selection.translated(self.geometry().topLeft()))
        else:
            self.cancelled.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.hide()
            self.cancelled.emit()
