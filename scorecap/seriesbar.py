"""The small bar a capture series leaves on screen: what is taken, what comes next."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import icons
from .theme import Palette, stylesheet

THUMB_SIZE = QSize(120, 40)
SCREEN_MARGIN_PX = 24


def bar_position(screen: QRect, size: QSize, wanted: QPoint | None) -> QPoint:
    """Where the bar goes: `wanted`, or low and centred, and always on `screen`.

    Low because a score is read from the top of the window down, and a bar
    over the system being captured would have to be moved out of the way.
    """
    if wanted is None:
        wanted = QPoint(
            screen.center().x() - size.width() // 2,
            screen.bottom() - size.height() - SCREEN_MARGIN_PX,
        )
    return QPoint(
        max(screen.left(), min(wanted.x(), screen.right() - size.width() + 1)),
        max(screen.top(), min(wanted.y(), screen.bottom() - size.height() + 1)),
    )


def _left_end(path: Path, crop: tuple[int, int, int, int] | None) -> QPixmap:
    """The start of a capture: clef, first bar and lyrics say which line it is."""
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return pixmap
    if crop is not None:
        left, top, right, bottom = crop
        pixmap = pixmap.copy(QRect(left, top, right - left, bottom - top))
    scaled = pixmap.scaled(
        THUMB_SIZE,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    return scaled.copy(QRect(QPoint(0, 0), THUMB_SIZE))


class SeriesBar(QWidget):
    """Parentless like the overlay: a child would go with the minimised window.

    It never takes the focus, so the browser keeps it and the next hotkey
    press works right away - clicking Undo here does not interrupt the series.
    """

    retake_requested = Signal()
    undo_requested = Signal()
    done_requested = Signal()

    def __init__(self, palette: Palette) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setObjectName("SeriesBar")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._palette = palette
        self._dragged_from: QPoint | None = None
        self._placed: QPoint | None = None  # kept across a series once moved

        self._thumb = QLabel()
        self._thumb.setFixedSize(THUMB_SIZE)
        self._thumb.setObjectName("SeriesThumb")
        self._title = QLabel()
        self._title.setObjectName("Heading")
        self._hint = QLabel()
        self._hint.setObjectName("Muted")
        words = QVBoxLayout()
        words.setSpacing(0)
        words.addWidget(self._title)
        words.addWidget(self._hint)

        self.retake_button = QPushButton(self.tr("Again"))
        self.retake_button.setObjectName("Quiet")
        self.retake_button.clicked.connect(self.retake_requested)
        self.undo_button = QPushButton(self.tr("Undo"))
        self.undo_button.setObjectName("Quiet")
        self.undo_button.clicked.connect(self.undo_requested)
        self.done_button = QPushButton(self.tr("Done"))
        self.done_button.setObjectName("Primary")
        self.done_button.clicked.connect(self.done_requested)
        for button in (self.retake_button, self.undo_button, self.done_button):
            button.setCursor(Qt.CursorShape.ArrowCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(12)
        row.addWidget(self._thumb)
        row.addLayout(words)
        row.addSpacing(8)
        row.addWidget(self.retake_button)
        row.addWidget(self.undo_button)
        row.addWidget(self.done_button)
        self.set_palette(palette)

    @property
    def title(self) -> str:
        return self._title.text()

    @property
    def hint(self) -> str:
        return self._hint.text()

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.setStyleSheet(stylesheet(palette))
        if icons.available():
            self.retake_button.setIcon(
                icons.icon(icons.RECAPTURE, palette.text, disabled=palette.text_muted)
            )
            self.undo_button.setIcon(
                icons.icon(icons.UNDO, palette.text, disabled=palette.text_muted)
            )
            self.done_button.setIcon(icons.icon(icons.DONE, palette.on_accent))

    def show_state(
        self,
        title: str,
        hint: str,
        path: Path | None = None,
        crop: tuple[int, int, int, int] | None = None,
    ) -> None:
        """Say where the series stands; `path` is the capture Undo would take back."""
        self._title.setText(title)
        self._hint.setText(hint)
        self._thumb.setVisible(path is not None)
        if path is not None:
            self._thumb.setPixmap(_left_end(path, crop))
        self.retake_button.setEnabled(path is not None)
        self.undo_button.setEnabled(path is not None)
        self.adjustSize()
        self.move(bar_position(self._screen_rect(), self.size(), self._placed))
        self.show()

    def _screen_rect(self) -> QRect:
        screen = (
            QGuiApplication.screenAt(QCursor.pos())
            or QGuiApplication.primaryScreen()
        )
        return screen.availableGeometry()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        # A bar in front of the passage has to be movable, and it has no title
        # bar to hold it by.
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragged_from = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._dragged_from is not None:
            wanted = event.globalPosition().toPoint() - self._dragged_from
            self._placed = bar_position(self._screen_rect(), self.size(), wanted)
            self.move(self._placed)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._dragged_from = None
