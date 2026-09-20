"""Non-destructive editing: the dialog only produces a rectangle and erasures.

Cropping decides which part of the capture is kept; the eraser whites out
small rectangles inside it - a page number, a stray mark. Neither touches the
file on disk: both are coordinates the export paints with.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
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
WHITE = QColor(255, 255, 255)
HANDLE_PX = 7
GRAB_PX = 8        # how close to an edge or corner the pointer takes hold of it
MIN_CROP_PX = 5
MIN_ERASE_PX = 2   # smaller than this is a click that missed, not an erasure

CANVAS_MIN = QSize(480, 360)   # the smallest the canvas may be squeezed to
SCREEN_SHARE = 0.8             # of the screen the dialog takes when it opens

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


def box_between(a: QPoint, b: QPoint, minimum: int) -> tuple[int, int, int, int] | None:
    """The rectangle two dragged points span, whichever way the drag went.

    None when it stays below `minimum` in either direction - a click that
    wandered a pixel should not become a rectangle.
    """
    left, right = sorted((a.x(), b.x()))
    top, bottom = sorted((a.y(), b.y()))
    if right - left < minimum or bottom - top < minimum:
        return None
    return left, top, right, bottom


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
    """Shows the shot scaled to fit and lets the user drag rectangles on it.

    In erase mode - where it starts, because erasing is the everyday job -
    a drag whites out the rectangle it spans. In crop mode a drag draws the
    crop, or adjusts an existing one: its corners and edges resize it, a drag
    inside moves it.
    """

    erasures_changed = Signal()

    def __init__(
        self,
        pixmap: QPixmap,
        crop: tuple[int, int, int, int] | None,
        erasures: tuple[tuple[int, int, int, int], ...] = (),
        palette: Palette = LIGHT,
    ) -> None:
        super().__init__()
        self._pixmap = pixmap
        self._crop = crop
        self._erasures = list(erasures)
        self._palette = palette
        self._mode = "erase"
        self._start: QPoint | None = None
        self._now: QPoint | None = None   # the far corner while erasing
        # While adjusting: the part held, the crop and source point at the start.
        self._drag: tuple[str, tuple[int, int, int, int], QPoint] | None = None
        self.setMinimumSize(CANVAS_MIN)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)  # the cursor shows what a drag would do

    @property
    def crop(self) -> tuple[int, int, int, int] | None:
        return self._crop

    @property
    def erasures(self) -> tuple[tuple[int, int, int, int], ...]:
        return tuple(self._erasures)

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._start = self._now = None
        self._drag = None
        self.setCursor(Qt.CrossCursor)
        self.update()

    def reset(self) -> None:
        """Back to the whole image. The erasures are a separate decision."""
        self._crop = None
        self.update()

    def undo_erase(self) -> None:
        if self._erasures:
            self._erasures.pop()
            self.erasures_changed.emit()
            self.update()

    def _display(self) -> QRect:
        return display_rect(self._pixmap.size(), self.size())

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self._palette.canvas))
        display = self._display()
        painter.drawPixmap(display, self._pixmap)
        # What the export will paint, shown where it will land.
        for erasure in self._erasures:
            painter.fillRect(self._box_rect(display, erasure), WHITE)
        selection = self._box_rect(display, self._held_crop())
        if self._crop is not None:
            self._dim_around(painter, display, selection)
            painter.setPen(QPen(QColor(self._palette.accent), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(selection)
        if self._mode == "crop":
            # Without a crop nothing falls away, but the corners still hold.
            self._paint_handles(painter, selection)
        else:
            self._paint_pending_erasure(painter, display)

    def _dim_around(self, painter: QPainter, display: QRect, selection: QRect) -> None:
        """Dim what falls away, the same language the capture overlay speaks."""
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

    def _paint_pending_erasure(self, painter: QPainter, display: QRect) -> None:
        if self._start is None or self._now is None:
            return
        rect = QRect(self._start, self._now).normalized()
        painter.fillRect(rect & display, WHITE)
        painter.setPen(QPen(QColor(self._palette.accent), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect & display)

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

    def _box_rect(self, display: QRect, box: tuple[int, int, int, int]) -> QRect:
        """Where a box in source pixels lands on the scaled image."""
        left, top, right, bottom = box
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
        handle = hit_test(self._box_rect(self._display(), self._held_crop()), point)
        if self._crop is None and handle == "move":
            return None  # nothing to move; a drag draws a new rectangle
        return handle

    def _source_point(self, point: QPoint) -> QPoint:
        return widget_to_source(point, self._display(), self._pixmap.size())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        if self._mode == "erase":
            self._start = self._now = point
            return
        handle = self._handle_at(point)
        if handle is not None:
            self._drag = (handle, self._held_crop(), self._source_point(point))
        else:
            self._start = point

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        if self._mode == "erase":
            if self._start is not None:
                self._now = point
                self.update()
            return
        if self._drag is not None:
            self._adjust(point)
        elif self._start is not None:
            self._set_crop(self._start, point)
        else:
            self.setCursor(CURSORS.get(self._handle_at(point), Qt.CrossCursor))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        if self._mode == "erase":
            if self._start is not None:
                self._add_erasure(self._start, point)
                self._start = self._now = None
            return
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

    def _add_erasure(self, start: QPoint, end: QPoint) -> None:
        box = box_between(
            self._source_point(start), self._source_point(end), MIN_ERASE_PX
        )
        if box is not None:
            self._erasures.append(box)
            self.erasures_changed.emit()
        self.update()

    def _set_crop(self, start: QPoint, end: QPoint) -> None:
        self._crop = box_between(
            self._source_point(start), self._source_point(end), MIN_CROP_PX
        )
        self.update()


class CropDialog(QDialog):
    def __init__(
        self,
        shot: Shot,
        parent: QWidget | None = None,
        palette: Palette = LIGHT,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit"))
        self._canvas = _CropCanvas(
            QPixmap(str(shot.path)), shot.crop, shot.erasures, palette
        )

        self._crop_mode = self._mode_button(self.tr("Crop"), "crop")
        self._crop_mode.setToolTip(self.tr("Drag out the part of the capture to keep"))
        self._erase_mode = self._mode_button(self.tr("Eraser"), "erase")
        self._erase_mode.setToolTip(
            self.tr("Drag over anything disturbing to paint it white")
        )
        self._erase_mode.setChecked(True)
        modes = QButtonGroup(self)
        modes.setExclusive(True)
        modes.addButton(self._crop_mode)
        modes.addButton(self._erase_mode)

        self._undo_erase_button = QPushButton(self.tr("Undo erasing"))
        self._undo_erase_button.setObjectName("Quiet")
        self._undo_erase_button.setToolTip(self.tr("Take back the last white rectangle"))
        self._undo_erase_button.clicked.connect(self.undo_erase)
        self._canvas.erasures_changed.connect(self._update_actions)

        reset_button = QPushButton(self.tr("Whole image"))
        reset_button.setObjectName("Quiet")
        reset_button.setToolTip(self.tr("Discard the crop and use the whole image"))
        reset_button.clicked.connect(self.reset)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(self.tr("Apply"))
        buttons.button(QDialogButtonBox.Cancel).setText(self.tr("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        tools = QHBoxLayout()
        tools.addWidget(self._crop_mode)
        tools.addWidget(self._erase_mode)
        tools.addSpacing(8)
        tools.addWidget(self._undo_erase_button)
        tools.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(reset_button)
        row.addStretch(1)
        row.addWidget(buttons)
        layout = QVBoxLayout(self)
        layout.addLayout(tools)
        layout.addWidget(self._canvas, 1)
        layout.addLayout(row)
        self._update_actions()
        self.resize(self._opening_size())

    def _mode_button(self, text: str, mode: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("Quiet")
        button.setCheckable(True)
        button.clicked.connect(lambda _checked, mode=mode: self.set_mode(mode))
        return button

    def _opening_size(self) -> QSize:
        """Most of the screen: erasing small marks needs a large view."""
        screen = (self.parentWidget() or self).screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return self.sizeHint()
        available = screen.availableGeometry().size()
        return QSize(
            int(available.width() * SCREEN_SHARE), int(available.height() * SCREEN_SHARE)
        )

    @property
    def crop(self) -> tuple[int, int, int, int] | None:
        return self._canvas.crop

    @property
    def erasures(self) -> tuple[tuple[int, int, int, int], ...]:
        return self._canvas.erasures

    def set_mode(self, mode: str) -> None:
        (self._erase_mode if mode == "erase" else self._crop_mode).setChecked(True)
        self._canvas.set_mode(mode)
        self._update_actions()

    def reset(self) -> None:
        self._canvas.reset()

    def undo_erase(self) -> None:
        self._canvas.undo_erase()

    def _update_actions(self) -> None:
        self._undo_erase_button.setEnabled(bool(self._canvas.erasures))
