"""Rasterise the built PDF so the preview always matches the export.

The pages are shown the way a proof looks on a desk: real paper on a dark
surface, with a soft shadow and the page number set in the gutter beside it.
"""

from __future__ import annotations

import pymupdf
from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .settings import A4_HEIGHT_PT, A4_WIDTH_PT
from .theme import LIGHT, Palette

PAGE_SPACING_PX = 28
GUTTER_PX = 34
SHADOW_BLUR = 24
SHADOW_MARGIN = 14
SCROLLBAR_PX = 16
RESIZE_SETTLE_MS = 120
MIN_ZOOM = 0.35
MAX_ZOOM = 3.0


def render_pages(pdf_bytes: bytes, zoom: float = 1.0) -> list[QImage]:
    if not pdf_bytes:
        return []
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        images: list[QImage] = []
        matrix = pymupdf.Matrix(zoom, zoom)
        for page in doc:
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = QImage(
                pixmap.samples,
                pixmap.width,
                pixmap.height,
                pixmap.stride,
                QImage.Format_RGB888,
            )
            images.append(image.copy())  # detach from the PyMuPDF buffer
        return images
    finally:
        doc.close()


def page_chrome_px() -> int:
    """Everything beside the sheet: canvas margins, both gutters, scrollbar."""
    return 2 * PAGE_SPACING_PX + 2 * (GUTTER_PX + 12) + SCROLLBAR_PX


def fit_zoom(viewport_width: int) -> float:
    """Zoom at which one sheet and its gutters fit across the viewport."""
    return _clamp((viewport_width - page_chrome_px()) / A4_WIDTH_PT)


def _clamp(zoom: float) -> float:
    return max(MIN_ZOOM, min(MAX_ZOOM, zoom))


class PageView(QWidget):
    """One page: the sheet itself, with its number set beside it."""

    # Page number (from zero) and where on the sheet it was clicked, in
    # rendered pixels. The page carries its own number so the preview can
    # connect a plain method rather than a closure over itself.
    clicked = Signal(int, QPoint)

    def __init__(self, image: QImage, number: int, palette: Palette) -> None:
        super().__init__()
        self._index = number - 1
        label = QLabel()
        label.setObjectName("PageSheet")
        self._sheet = label
        self.set_image(image)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(SHADOW_BLUR)
        shadow.setColor(QColor(0, 0, 0, 90))
        shadow.setOffset(0, 3)
        label.setGraphicsEffect(shadow)

        number_label = QLabel(str(number))
        number_label.setObjectName("PageNumber")
        number_label.setFixedWidth(GUTTER_PX)
        number_label.setAlignment(Qt.AlignRight | Qt.AlignTop)

        row = QHBoxLayout(self)
        # The margin is what the drop shadow is drawn into; without it Qt
        # clips the shadow at the widget edge.
        row.setContentsMargins(0, SHADOW_MARGIN, 0, SHADOW_MARGIN)
        row.setSpacing(12)
        row.addWidget(number_label, 0, Qt.AlignTop)
        row.addWidget(label, 0, Qt.AlignTop)
        row.addSpacing(GUTTER_PX + 12)  # mirror the number column

    def set_image(self, image: QImage) -> None:
        """Swap the rendered sheet in place; the widget itself stays."""
        self._sheet.setPixmap(QPixmap.fromImage(image))
        self._sheet.setFixedSize(image.size())

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        point = self._sheet.mapFrom(self, event.position().toPoint())
        if self._sheet.rect().contains(point):
            self.clicked.emit(self._index, point)
        super().mousePressEvent(event)


class PreviewWidget(QScrollArea):
    # Page number (from zero) and the point clicked, in PDF points.
    clicked_at = Signal(int, float, float)

    def __init__(self, palette: Palette = LIGHT) -> None:
        super().__init__()
        self.setObjectName("Preview")
        self._palette = palette
        self._zoom = 1.0
        self._fit = True
        self._pdf_bytes = b""
        self._page_count = 0
        self._rebuilding = False
        self._pages: list[PageView] = []
        # A drag delivers dozens of resize events; render once it settles.
        self._refit_timer = QTimer(self)
        self._refit_timer.setSingleShot(True)
        self._refit_timer.setInterval(RESIZE_SETTLE_MS)
        self._refit_timer.timeout.connect(self._refit)

        self._container = QWidget()
        self._container.setObjectName("PreviewCanvas")
        self._layout = QVBoxLayout(self._container)
        self._layout.setSpacing(PAGE_SPACING_PX)
        self._layout.setContentsMargins(
            PAGE_SPACING_PX, PAGE_SPACING_PX, PAGE_SPACING_PX, PAGE_SPACING_PX
        )
        self._layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setWidget(self._container)
        self.setWidgetResizable(True)

    @property
    def page_count(self) -> int:
        return self._page_count

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def fits_width(self) -> bool:
        return self._fit

    def page_views(self) -> list[PageView]:
        return list(self._pages)

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._rebuild()

    def _fit_source_width(self) -> int:
        """Width to fit into, measured so a scrollbar cannot change it.

        The viewport narrows when the vertical scrollbar appears and widens
        again while the pages are torn down for a rebuild. Fitting to that
        number makes the zoom chase its own scrollbar forever, so measure the
        scroll area instead - page_chrome_px() already reserves the bar.
        """
        return self.width() - 2 * self.frameWidth()

    def set_zoom(self, zoom: float) -> None:
        self._fit = False
        self._zoom = _clamp(zoom)
        self._rebuild()

    def fit_to_width(self) -> None:
        self._fit = True
        self._zoom = fit_zoom(self._fit_source_width())
        self._rebuild()

    def set_pdf(self, pdf_bytes: bytes) -> None:
        self._pdf_bytes = pdf_bytes
        if self._fit:
            self._zoom = fit_zoom(self._fit_source_width())
        self._rebuild()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        if self._fit and not self._rebuilding:
            self._refit_timer.start()  # restarts on every event of a drag

    def _refit(self) -> None:
        new_zoom = fit_zoom(self._fit_source_width())
        if abs(new_zoom - self._zoom) > 0.01:
            self._zoom = new_zoom
            self._rebuild()

    def _page_clicked(self, index: int, point: QPoint) -> None:
        """Rendered pixels back to the points the layout worked in."""
        self.clicked_at.emit(index, point.x() / self._zoom, point.y() / self._zoom)

    def _rebuild(self) -> None:
        """Bring the page widgets up to date without ever emptying the canvas.

        Deleting every page and adding new ones leaves Qt at least one frame
        with nothing on the canvas - visible as flicker whenever several
        rebuilds follow each other, as they do while a window opens. Existing
        pages get new pixmaps instead; only a changed page count adds or
        removes widgets at the end.
        """
        # Swapping pixmaps resizes this widget; ignore the resize events that
        # causes rather than scheduling another rebuild.
        self._rebuilding = True
        try:
            images = render_pages(self._pdf_bytes, self._zoom)
            self._page_count = len(images)
            for page, image in zip(self._pages, images):
                page.set_image(image)
            for number in range(len(self._pages) + 1, len(images) + 1):
                page = PageView(images[number - 1], number, self._palette)
                page.clicked.connect(self._page_clicked)
                self._pages.append(page)
                self._layout.addWidget(page, 0, Qt.AlignHCenter)
            while len(self._pages) > len(images):
                page = self._pages.pop()
                self._layout.removeWidget(page)
                page.deleteLater()
        finally:
            self._rebuilding = False
