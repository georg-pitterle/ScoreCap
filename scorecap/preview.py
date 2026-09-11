"""Rasterise the built PDF so the preview always matches the export.

The pages are shown the way a proof looks on a desk: real paper on a dark
surface, with a soft shadow and the page number set in the gutter beside it.
"""

from __future__ import annotations

import pymupdf
from PySide6.QtCore import QRect, QSize, Qt
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

    def __init__(self, image: QImage, number: int, palette: Palette) -> None:
        super().__init__()
        label = QLabel()
        label.setObjectName("PageSheet")
        label.setPixmap(QPixmap.fromImage(image))
        label.setFixedSize(image.size())
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


class PreviewWidget(QScrollArea):
    def __init__(self, palette: Palette = LIGHT) -> None:
        super().__init__()
        self.setObjectName("Preview")
        self._palette = palette
        self._zoom = 1.0
        self._fit = True
        self._pdf_bytes = b""
        self._page_count = 0

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

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._rebuild()

    def set_zoom(self, zoom: float) -> None:
        self._fit = False
        self._zoom = _clamp(zoom)
        self._rebuild()

    def fit_to_width(self) -> None:
        self._fit = True
        self._zoom = fit_zoom(self.viewport().width())
        self._rebuild()

    def set_pdf(self, pdf_bytes: bytes) -> None:
        self._pdf_bytes = pdf_bytes
        if self._fit:
            self._zoom = fit_zoom(self.viewport().width())
        self._rebuild()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        if self._fit:
            new_zoom = fit_zoom(self.viewport().width())
            if abs(new_zoom - self._zoom) > 0.01:
                self._zoom = new_zoom
                self._rebuild()

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild(self) -> None:
        self._clear()
        images = render_pages(self._pdf_bytes, self._zoom)
        self._page_count = len(images)
        for number, image in enumerate(images, start=1):
            self._layout.addWidget(PageView(image, number, self._palette), 0, Qt.AlignHCenter)
