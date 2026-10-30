"""The list of captures: a thumbnail strip with the numbers that matter."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
)

from .layout import effective_dpi
from .model import Shot
from .settings import Settings
from .theme import Palette, font_families

ROW_HEIGHT = 64
THUMB_WIDTH = 96
THUMB_HEIGHT = 48
PADDING = 10
GAP = 10
# Every crop and every erasure makes a thumbnail of its own; without a limit
# a long session of editing keeps all of them.
THUMB_CACHE = 64

DATA_ROLE = Qt.UserRole + 1


@dataclass(frozen=True)
class RowData:
    """Everything one row shows, worked out away from the painting code."""

    number: int
    size_label: str
    chip: str | None
    chip_kind: str | None  # "warn" or "missing"
    path: str | None
    crop: tuple[int, int, int, int] | None = None
    erasures: tuple[tuple[int, int, int, int], ...] = ()
    page: int | None = None  # from one, as printed; None until it is laid out


def row_data(
    index: int,
    shot: Shot,
    settings: Settings,
    missing: bool,
    page: int | None = None,
) -> RowData:
    width, height = shot.effective_size
    if missing:
        missing_file = QCoreApplication.translate("ShotList", "File missing")
        return RowData(index + 1, f"{width}×{height}", missing_file, "missing", None)
    dpi = effective_dpi(shot.effective_size, settings)
    chip = f"{dpi:.0f} dpi" if dpi < settings.min_dpi else None
    return RowData(
        number=index + 1,
        size_label=f"{width}×{height}",
        chip=chip,
        chip_kind="warn" if chip else None,
        path=str(shot.path),
        crop=shot.crop,
        erasures=shot.erasures,
        page=page,
    )


def _where(data: RowData) -> str:
    """Where the capture landed, which is what its row is looked at for."""
    if data.page is None:
        return data.size_label
    return QCoreApplication.translate("ShotList", "page {page}").format(page=data.page)


class ShotDelegate(QStyledItemDelegate):
    def __init__(self, palette: Palette) -> None:
        super().__init__()
        self.palette = palette
        self._thumbs: dict[tuple, QPixmap] = {}

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 (Qt naming)
        return QSize(240, ROW_HEIGHT)

    def _thumbnail(
        self,
        path: str,
        crop: tuple[int, int, int, int] | None = None,
        erasures: tuple[tuple[int, int, int, int], ...] = (),
    ) -> QPixmap | None:
        """A staff strip is far wider than the row, so fill the box and crop.

        Fitting the whole strip would shrink it to an illegible hairline, so
        the notation keeps a readable size and the row shows a part of it.
        """
        key = (path, crop, erasures)
        if key not in self._thumbs:
            pixmap = QPixmap(path)
            if erasures and not pixmap.isNull():
                # Whited out here too, so the row shows what the export will.
                painter = QPainter(pixmap)
                try:
                    for left, top, right, bottom in erasures:
                        painter.fillRect(
                            QRect(left, top, right - left, bottom - top), Qt.white
                        )
                finally:
                    painter.end()
            if crop is not None and not pixmap.isNull():
                # A scanned system sits in a band of the page; show the system.
                left, top, right, bottom = crop
                pixmap = pixmap.copy(QRect(left, top, right - left, bottom - top))
            if len(self._thumbs) >= THUMB_CACHE:
                self._thumbs.pop(next(iter(self._thumbs)))  # the oldest goes
            self._thumbs[key] = (
                QPixmap()
                if pixmap.isNull()
                else pixmap.scaled(
                    THUMB_WIDTH * 2,
                    THUMB_HEIGHT * 2,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
            )
        thumb = self._thumbs[key]
        return None if thumb.isNull() else thumb

    def paint(self, painter: QPainter, option, index) -> None:
        data: RowData = index.data(DATA_ROLE)
        if data is None:
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect
        self._paint_row_background(painter, rect, option)

        thumb_rect = QRect(
            rect.left() + PADDING,
            rect.top() + (rect.height() - THUMB_HEIGHT) // 2,
            THUMB_WIDTH,
            THUMB_HEIGHT,
        )
        self._paint_thumbnail(painter, thumb_rect, data)

        text_left = thumb_rect.right() + GAP
        self._paint_number(painter, rect, text_left, data)
        if option.state & QStyle.State_HasFocus:
            # The list hides Qt's own focus frame; the keyboard needs one.
            painter.setPen(QPen(QColor(self.palette.accent), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.restore()

    def _paint_row_background(self, painter: QPainter, rect: QRect, option) -> None:
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        if not (selected or hovered):
            return
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self.palette.accent_soft))
        painter.drawRect(rect)
        if selected:
            # A bar on the leading edge, the way a file list marks its row.
            painter.setBrush(QColor(self.palette.accent))
            painter.drawRect(QRect(rect.left(), rect.top(), 3, rect.height()))

    def _paint_thumbnail(self, painter: QPainter, rect: QRect, data: RowData) -> None:
        painter.setPen(QPen(QColor(self.palette.border), 1))
        painter.setBrush(QColor(self.palette.paper))
        painter.drawRect(rect)
        thumb = (
            self._thumbnail(data.path, data.crop, data.erasures) if data.path else None
        )
        if thumb is None:
            return
        inner = rect.adjusted(1, 1, -1, -1)
        source = QRect(0, 0, inner.width() * 2, inner.height() * 2)
        source.moveCenter(thumb.rect().center())
        # From the left: clef, first bar and first words tell the lines apart.
        source.moveLeft(0)
        painter.drawPixmap(inner, thumb, source)

    def _paint_number(self, painter: QPainter, row: QRect, left: int, data: RowData) -> None:
        mono = QFont()
        mono.setFamilies(font_families(self.palette.font_mono))
        mono.setPointSize(9)
        painter.setFont(mono)
        painter.setPen(QColor(self.palette.text))
        painter.drawText(
            QRect(left, row.top() + 12, row.right() - left - PADDING, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"{data.number:>2}  {_where(data)}",
        )
        if data.chip:
            self._paint_chip(painter, QRect(left, row.top() + 32, 140, 18), data)

    def _paint_chip(self, painter: QPainter, rect: QRect, data: RowData) -> None:
        warn = data.chip_kind == "warn"
        background = self.palette.warn_soft if warn else self.palette.danger_soft
        foreground = self.palette.warn if warn else self.palette.danger
        font = QFont()
        font.setFamilies(font_families(self.palette.font_ui))
        font.setPointSize(8)
        painter.setFont(font)
        width = QFontMetrics(font).horizontalAdvance(data.chip) + 14
        chip = QRect(rect.left(), rect.top(), width, rect.height())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(chip, 3, 3)
        painter.setPen(QColor(foreground))
        painter.drawText(chip, Qt.AlignCenter, data.chip)


class ShotList(QListWidget):
    edit_requested = Signal()
    delete_requested = Signal()
    shift_requested = Signal(int)  # one row up (-1) or down (+1)

    def __init__(self, palette: Palette) -> None:
        super().__init__()
        self._delegate = ShotDelegate(palette)
        self.setItemDelegate(self._delegate)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

    def set_palette(self, palette: Palette) -> None:
        self._delegate.palette = palette
        self.viewport().update()

    def selected_rows(self) -> list[int]:
        return sorted(index.row() for index in self.selectedIndexes())

    def order(self) -> list[int]:
        """Which document row stands in each list row, after a drag."""
        return [
            self.item(row).data(DATA_ROLE).number - 1 for row in range(self.count())
        ]

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        # Reordering by drag alone would shut out everyone without a mouse.
        alt = event.modifiers() == Qt.KeyboardModifier.AltModifier
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.edit_requested.emit()
        elif event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit()
        elif alt and event.key() == Qt.Key.Key_Up:
            self.shift_requested.emit(-1)
        elif alt and event.key() == Qt.Key.Key_Down:
            self.shift_requested.emit(1)
        else:
            super().keyPressEvent(event)

    def add_row(self, data: RowData) -> None:
        item = QListWidgetItem()
        item.setData(DATA_ROLE, data)
        item.setSizeHint(QSize(240, ROW_HEIGHT))
        words = self.tr("Capture {number}, {size} px").format(
            number=data.number, size=data.size_label
        ) + (f" — {data.chip}" if data.chip else "")
        if data.page is not None:
            words += ", " + _where(data)
        # A painted row says nothing to a screen reader, and tooltips do not
        # reach one: the words need a role of their own.
        item.setData(Qt.ItemDataRole.AccessibleTextRole, words)
        item.setToolTip(
            words
            + ("" if data.path is None else "\n" + self.tr("Double-click to edit"))
        )
        self.addItem(item)
