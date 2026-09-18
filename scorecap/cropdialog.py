"""Non-destructive crop: the dialog only produces a rectangle."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .model import Shot
from .theme import LIGHT, Palette

DIM = QColor(0, 0, 0, 120)
HANDLE_PX = 7
GRAB_PX = 8        # how close to an edge or corner the pointer takes hold of it
MIN_CROP_PX = 5

# What dragging from each part of the selection changes, and how it looks.
CURSORS = {
    "tl": Qt.SizeFDiagCursor,
    "br": Qt.SizeFDiagCursor,
    "tr": Qt.SizeBDiagCursor,
    "bl": Qt.SizeBDiagCursor,
    "l": Qt.SizeHorCursor,
    "r": Qt.SizeHorCursor,
    "t": Qt.SizeVerCursor,
    "b": Qt.SizeVerCursor,
    "move": Qt.SizeAllCursor,
}


def display_rect(source: QSize, viewport: QSize) -> QRect:
    scale = min(viewport.width() / source.width(), viewport.height() / source.height())
    width = round(source.width() * scale)
    height = round(source.height() * scale)
    return QRect(
        (viewport.width() - width) // 2,
        (viewport.height() - height) // 2,
        width,
        height,
    )


def widget_to_source(point: QPoint, display: QRect, source: QSize) -> QPoint:
    x = (point.x() - display.x()) * source.width() / display.width()
    y = (point.y() - display.y()) * source.height() / display.height()
    return QPoint(
        int(min(max(round(x), 0), source.width())),
        int(min(max(round(y), 0), source.height())),
    )


def hit_test(selection: QRect, point: QPoint, grab: int = GRAB_PX) -> str | None:
    """Which part of the selection the pointer is on.

    "tl", "tr", "bl", "br" for a corner, "l", "r", "t", "b" for an edge,
    "move" inside, None outside - where a drag starts a new rectangle.
    """
    left, top = selection.left(), selection.top()
    right, bottom = left + selection.width(), top + selection.height()
    x, y = point.x(), point.y()
    if not (left - grab <= x <= right + grab and top - grab <= y <= bottom + grab):
        return None
    vertical = "t" if abs(y - top) <= grab else "b" if abs(y - bottom) <= grab else ""
    horizontal = "l" if abs(x - left) <= grab else "r" if abs(x - right) <= grab else ""
    return (vertical + horizontal) or "move"


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def adjust_crop(
    crop: tuple[int, int, int, int],
    handle: str,
    dx: int,
    dy: int,
    size: tuple[int, int],
) -> tuple[int, int, int, int]:
    """The crop after dragging one of its parts by (dx, dy) source pixels.

    Edges stay on the image and never cross; a moved crop keeps its size.
    """
    left, top, right, bottom = crop
    width, height = size
    if handle == "move":
        dx = _clamp(dx, -left, width - right)
        dy = _clamp(dy, -top, height - bottom)
        return left + dx, top + dy, right + dx, bottom + dy
    if "l" in handle:
        left = _clamp(left + dx, 0, right - MIN_CROP_PX)
    if "r" in handle:
        right = _clamp(right + dx, left + MIN_CROP_PX, width)
    if "t" in handle:
        top = _clamp(top + dy, 0, bottom - MIN_CROP_PX)
    if "b" in handle:
        bottom = _clamp(bottom + dy, top + MIN_CROP_PX, height)
    return left, top, right, bottom


class _CropCanvas(QWidget):
    """Shows the shot scaled to fit and lets the user drag a rectangle on it.

    An existing rectangle can be adjusted instead of drawn anew: its corners
    and edges resize it, a drag inside moves it.
    """

    def __init__(
        self,
        pixmap: QPixmap,
        crop: tuple[int, int, int, int] | None,
        palette: Palette,
    ) -> None:
        super().__init__()
        self._pixmap = pixmap
        self._crop = crop
        self._palette = palette
        self._start: QPoint | None = None
        # While adjusting: the part held, the crop and source point at the start.
        self._drag: tuple[str, tuple[int, int, int, int], QPoint] | None = None
        self.setMinimumSize(480, 360)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)  # the cursor shows what a drag would do

    @property
    def crop(self) -> tuple[int, int, int, int] | None:
        return self._crop

    def reset(self) -> None:
        self._crop = None
        self.update()

    def _display(self) -> QRect:
        return display_rect(self._pixmap.size(), self.size())

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self._palette.canvas))
        display = self._display()
        painter.drawPixmap(display, self._pixmap)
        selection = self._selection_rect(display)
        if self._crop is None:
            # Nothing falls away, but the corners can still be taken hold of.
            self._paint_handles(painter, selection)
            return
        # Dim what falls away, the same language the capture overlay speaks.
        for outside in (
            QRect(display.left(), display.top(), display.width(), selection.top() - display.top()),
            QRect(
                display.left(),
                selection.bottom(),
                display.width(),
                display.bottom() - selection.bottom(),
            ),
            QRect(display.left(), selection.top(), selection.left() - display.left(), selection.height()),
            QRect(
                selection.right(),
                selection.top(),
                display.right() - selection.right(),
                selection.height(),
            ),
        ):
            painter.fillRect(outside, DIM)
        painter.setPen(QPen(QColor(self._palette.accent), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(selection)
        self._paint_handles(painter, selection)

    def _paint_handles(self, painter: QPainter, selection: QRect) -> None:
        painter.setBrush(QColor(self._palette.accent))
        painter.setPen(Qt.NoPen)
        for corner in (
            selection.topLeft(),
            selection.topRight(),
            selection.bottomLeft(),
            selection.bottomRight(),
        ):
            handle = QRect(0, 0, HANDLE_PX, HANDLE_PX)
            handle.moveCenter(corner)
            painter.drawRect(handle)

    def _selection_rect(self, display: QRect) -> QRect:
        left, top, right, bottom = self._held_crop()
        source = self._pixmap.size()
        scale_x = display.width() / source.width()
        scale_y = display.height() / source.height()
        return QRect(
            display.x() + round(left * scale_x),
            display.y() + round(top * scale_y),
            round((right - left) * scale_x),
            round((bottom - top) * scale_y),
        )

    def _held_crop(self) -> tuple[int, int, int, int]:
        """The crop, or without one the whole image, whose edges can be held."""
        if self._crop is not None:
            return self._crop
        return (0, 0, self._pixmap.width(), self._pixmap.height())

    def _handle_at(self, point: QPoint) -> str | None:
        handle = hit_test(self._selection_rect(self._display()), point)
        if self._crop is None and handle == "move":
            return None  # nothing to move; a drag draws a new rectangle
        return handle

    def _source_point(self, point: QPoint) -> QPoint:
        return widget_to_source(point, self._display(), self._pixmap.size())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        handle = self._handle_at(point)
        if handle is not None:
            self._drag = (handle, self._held_crop(), self._source_point(point))
        else:
            self._start = point

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        if self._drag is not None:
            self._adjust(point)
        elif self._start is not None:
            self._set_crop(self._start, point)
        else:
            self.setCursor(CURSORS.get(self._handle_at(point), Qt.CrossCursor))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        if self._drag is not None:
            self._adjust(point)
            self._drag = None
        elif self._start is not None:
            self._set_crop(self._start, point)
            self._start = None

    def _adjust(self, point: QPoint) -> None:
        handle, crop, origin = self._drag
        now = self._source_point(point)
        source = self._pixmap.size()
        self._crop = adjust_crop(
            crop,
            handle,
            now.x() - origin.x(),
            now.y() - origin.y(),
            (source.width(), source.height()),
        )
        self.update()

    def _set_crop(self, start: QPoint, end: QPoint) -> None:
        display = self._display()
        source = self._pixmap.size()
        a = widget_to_source(start, display, source)
        b = widget_to_source(end, display, source)
        left, right = sorted((a.x(), b.x()))
        top, bottom = sorted((a.y(), b.y()))
        too_small = right - left < MIN_CROP_PX or bottom - top < MIN_CROP_PX
        self._crop = None if too_small else (left, top, right, bottom)
        self.update()


class CropDialog(QDialog):
    def __init__(
        self,
        shot: Shot,
        parent: QWidget | None = None,
        palette: Palette = LIGHT,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Zuschneiden")
        self._canvas = _CropCanvas(QPixmap(str(shot.path)), shot.crop, palette)
        reset_button = QPushButton("Ganzes Bild")
        reset_button.setObjectName("Quiet")
        reset_button.setToolTip("Zuschnitt verwerfen und den vollen Screenshot verwenden")
        reset_button.clicked.connect(self.reset)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Übernehmen")
        buttons.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(reset_button)
        row.addStretch(1)
        row.addWidget(buttons)
        layout = QVBoxLayout(self)
        layout.addWidget(self._canvas, 1)
        layout.addLayout(row)

    @property
    def crop(self) -> tuple[int, int, int, int] | None:
        return self._canvas.crop

    def reset(self) -> None:
        self._canvas.reset()
