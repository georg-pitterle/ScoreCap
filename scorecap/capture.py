"""Full-screen selection overlay and the screen grab behind it."""

from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .model import Shot

MIN_SELECTION_PX = 20
DIM_COLOR = QColor(0, 0, 0, 110)
BORDER_COLOR = QColor(255, 255, 255)
CAPTION_TOP_PX = 24
KEY_STEP_PX = 10
FINE_STEP_PX = 1
ARROWS = {
    Qt.Key.Key_Left: (-1, 0),
    Qt.Key.Key_Right: (1, 0),
    Qt.Key.Key_Up: (0, -1),
    Qt.Key.Key_Down: (0, 1),
}


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
    cancelled = Signal()  # Esc: the user is done
    missed = Signal()     # a click or a slip of the mouse: the series goes on
    retake = Signal()     # the last capture was wrong: back to it, series running

    def __init__(self) -> None:
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self._start: QPoint | None = None
        self._current: QPoint | None = None
        self._caption = ""

    def start(self, caption: str = "") -> None:
        """Dim the screen; `caption` stands at the top of the one in use."""
        self._start = None
        self._current = None
        self._caption = caption
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
        self._paint_caption(painter)
        selection = self._selection()
        if selection.isNull():
            return
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(selection, Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setPen(QPen(BORDER_COLOR, 1))
        painter.drawRect(selection.adjusted(0, 0, -1, -1))

    def _paint_caption(self, painter: QPainter) -> None:
        if not self._caption:
            return
        screen = (
            QGuiApplication.screenAt(QCursor.pos())
            or QGuiApplication.primaryScreen()
        )
        area = screen.geometry().translated(-self.geometry().topLeft())
        painter.setPen(BORDER_COLOR)
        painter.drawText(
            area.adjusted(0, CAPTION_TOP_PX, 0, 0),
            Qt.AlignHCenter | Qt.AlignTop,
            self._caption,
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._start = event.position().toPoint()
            self._current = self._start
            self.update()
        elif event.button() == Qt.RightButton:
            if self._start is None:
                self.retake.emit()
                return
            # Seen in time: the drag goes, nothing was captured, nothing ends.
            self._start = self._current = None
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._start is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton or self._start is None:
            return
        self._finish()

    def _finish(self) -> None:
        selection = self._selection()
        self.hide()
        if is_valid_selection(selection):
            self.selected.emit(selection.translated(self.geometry().topLeft()))
        else:
            self.missed.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.hide()
            self.cancelled.emit()
        elif event.key() == Qt.Key_Backspace:
            self.retake.emit()
        elif event.key() in ARROWS:
            self._move_pointer(event)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._anchor_or_finish()

    def _pointer(self) -> QPoint:
        """Where the keyboard stands: at the far corner, else at the mouse."""
        if self._current is not None:
            return self._current
        return self.mapFromGlobal(QCursor.pos())

    def _move_pointer(self, event) -> None:
        """The arrows do what the mouse does; Shift goes pixel by pixel."""
        fine = event.modifiers() & Qt.ShiftModifier
        step = FINE_STEP_PX if fine else KEY_STEP_PX
        dx, dy = ARROWS[event.key()]
        moved = self._pointer() + QPoint(dx * step, dy * step)
        QCursor.setPos(self.mapToGlobal(moved))
        self._current = moved
        self.update()

    def _anchor_or_finish(self) -> None:
        """Enter sets the first corner, and the second one ends the selection."""
        if self._start is None:
            self._start = self._pointer()
            self._current = self._start
            self.update()
        else:
            self._finish()
