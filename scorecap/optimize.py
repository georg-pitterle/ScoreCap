"""Shrink an existing PDF by re-encoding its images losslessly.

Written for PDFs ScoreCap produced before it compressed its output, but it
runs on any PDF, so it is careful: it only rewrites an image when that makes
it smaller, keeps colour where there is colour, leaves images with
transparency alone, and never returns a file bigger than the one it got.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import pymupdf
from PIL import Image, ImageChops
from PySide6.QtCore import QCoreApplication

log = logging.getLogger(__name__)

# A pixel counts as coloured when its channels differ by more than this, and
# an image stays in colour once more than this share of its pixels do. The
# margins absorb the faint tints of screenshots and JPEG noise.
CHROMA_THRESHOLD = 24
COLOURED_SHARE = 0.001


@dataclass(frozen=True)
class OptimizeResult:
    data: bytes
    before: int
    after: int
    images_rewritten: int


def _is_achromatic(image: Image.Image) -> bool:
    red, green, blue = image.split()
    spread = ImageChops.lighter(
        ImageChops.difference(red, green), ImageChops.difference(green, blue)
    )
    coloured = sum(spread.histogram()[CHROMA_THRESHOLD + 1 :])
    return coloured <= COLOURED_SHARE * image.width * image.height


def _as_pil(pixmap: pymupdf.Pixmap) -> Image.Image | None:
    """The image as Pillow sees it, or None when it is not safe to touch."""
    if pixmap.alpha:
        return None
    if pixmap.n == 1:
        return Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
    if pixmap.n != 3:  # CMYK and friends: bring them into RGB first
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def _encode(image: Image.Image) -> bytes:
    if image.mode == "RGB" and _is_achromatic(image):
        image = image.convert("L")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def optimize_pdf(data: bytes) -> OptimizeResult:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as error:
        raise ValueError(
            QCoreApplication.translate("optimize", "The file is not a readable PDF.")
        ) from error
    try:
        rewritten = 0
        done: set[int] = set()
        for page in doc:
            for info in page.get_images(full=True):
                xref, smask = info[0], info[1]
                if xref in done:
                    continue
                done.add(xref)
                if smask:
                    continue  # transparency: re-encoding would drop the mask
                try:
                    image = _as_pil(pymupdf.Pixmap(doc, xref))
                except Exception as error:
                    log.info("image %s skipped: %s", xref, error)
                    continue
                if image is None:
                    continue
                candidate = _encode(image)
                if len(candidate) >= len(doc.xref_stream_raw(xref)):
                    continue  # already smaller as it is, e.g. a JPEG photo
                page.replace_image(xref, stream=candidate)
                rewritten += 1
        shrunk = doc.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        doc.close()

    if len(shrunk) >= len(data):
        return OptimizeResult(data, len(data), len(data), 0)
    return OptimizeResult(shrunk, len(data), len(shrunk), rewritten)
