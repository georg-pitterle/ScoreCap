"""Turn a layout into PDF bytes. These same bytes drive the preview."""

from __future__ import annotations

import io
from typing import Sequence

import pymupdf
from PIL import Image
from PySide6.QtCore import QCoreApplication

from .erase import apply as erase
from .layout import Page
from .model import Shot
from .scan import finish
from .settings import A4_HEIGHT_PT, A4_WIDTH_PT, MM_TO_PT, Settings

FOOTER_FONT = "helv"
FOOTER_SIZE = 9.0
FOOTER_COLOR = (0.4, 0.4, 0.4)
FOOTER_BASELINE_MM = 8.0


def _png_bytes(shot: Shot, settings: Settings) -> bytes:
    """Load the shot, apply its crop, and re-encode losslessly in grey.

    Notation is black on white, so colour carries nothing but a third of the
    bytes. Grey keeps the anti-aliased edges that make staves look clean -
    pure black and white would not: at screenshot resolution it makes staff
    lines of uneven weight.

    Scans are the exception: at scanner resolution black and white prints
    cleanly and makes the file far smaller, so the setting decides for them.
    """
    with Image.open(shot.path) as image:
        image = image.convert("L")
        # Erasures are in whole-image coordinates, so they go on before the crop.
        image = erase(image, shot.erasures)
        if shot.crop is not None:
            image = image.crop(shot.crop)
        if shot.scan and settings.scan_mode != "grey":
            image = finish(image, "bw")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
    return buffer.getvalue()


def build(shots: Sequence[Shot], pages: Sequence[Page], settings: Settings) -> bytes:
    if not pages:
        return b""  # PyMuPDF cannot serialise a zero-page document
    doc = pymupdf.open()
    try:
        total = len(pages)
        for number, page in enumerate(pages, start=1):
            pdf_page = doc.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
            for placement in page.placements:
                rect = pymupdf.Rect(
                    placement.x,
                    placement.y,
                    placement.x + placement.w,
                    placement.y + placement.h,
                )
                pdf_page.insert_image(rect, stream=_png_bytes(shots[placement.index], settings))
            if settings.footer_enabled:
                text = QCoreApplication.translate("pdf", "{page} of {total}").format(
                    page=number, total=total
                )
                width = pymupdf.get_text_length(
                    text, fontname=FOOTER_FONT, fontsize=FOOTER_SIZE
                )
                pdf_page.insert_text(
                    (
                        (A4_WIDTH_PT - width) / 2.0,
                        A4_HEIGHT_PT - FOOTER_BASELINE_MM * MM_TO_PT,
                    ),
                    text,
                    fontname=FOOTER_FONT,
                    fontsize=FOOTER_SIZE,
                    color=FOOTER_COLOR,
                )
        # PyMuPDF keeps inserted images as raw samples unless told to
        # compress on save: nine pages of screenshots came out at 58 MB.
        return doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()
