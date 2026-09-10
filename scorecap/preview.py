"""Rasterise the built PDF so the preview always matches the export."""

from __future__ import annotations

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

PAGE_SPACING_PX = 16


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


class PreviewWidget(QScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self._zoom = 1.0
        self._pdf_bytes = b""
        self._page_count = 0
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setSpacing(PAGE_SPACING_PX)
        self._layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setWidget(self._container)
        self.setWidgetResizable(True)

    @property
    def page_count(self) -> int:
        return self._page_count

    def set_zoom(self, zoom: float) -> None:
        self._zoom = zoom
        self._rebuild()

    def set_pdf(self, pdf_bytes: bytes) -> None:
        self._pdf_bytes = pdf_bytes
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
        for image in images:
            label = QLabel()
            label.setPixmap(QPixmap.fromImage(image))
            label.setAlignment(Qt.AlignCenter)
            self._layout.addWidget(label)
