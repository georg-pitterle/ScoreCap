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
MIN_CROP_PX = 5


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


class _CropCanvas(QWidget):
    """Shows the shot scaled to fit and lets the user drag a rectangle on it."""

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
        self.setMinimumSize(480, 360)
        self.setCursor(Qt.CrossCursor)

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
        if self._crop is None:
            return
        selection = self._selection_rect(display)
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
        left, top, right, bottom = self._crop
        source = self._pixmap.size()
        scale_x = display.width() / source.width()
        scale_y = display.height() / source.height()
        return QRect(
            display.x() + round(left * scale_x),
            display.y() + round(top * scale_y),
            round((right - left) * scale_x),
            round((bottom - top) * scale_y),
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._start = event.position().toPoint()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._start is not None:
            self._set_crop(self._start, event.position().toPoint())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._start is None:
            return
        self._set_crop(self._start, event.position().toPoint())
        self._start = None

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
