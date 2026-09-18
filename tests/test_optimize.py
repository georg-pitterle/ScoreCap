"""Shrinking an existing PDF must never damage it or make it bigger."""

import io
import random

import pymupdf
import pytest
from PIL import Image, ImageDraw

from scorecap.optimize import optimize_pdf


def staff_png(seed: int, width: int = 1200, height: int = 300) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for line in range(5):
        y = 80 + line * 22
        draw.line([20, y, width - 20, y], fill=(20, 20, 20), width=2)
    for step, x in enumerate(range(60 + seed * 7, width - 60, 70)):
        y = 90 + ((step * 5 + seed * 3) % 9) * 11
        draw.ellipse([x, y, x + 22, y + 16], fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def colour_png() -> bytes:
    image = Image.new("RGB", (400, 200))
    draw = ImageDraw.Draw(image)
    for x in range(400):
        draw.line([x, 0, x, 200], fill=(x * 255 // 400, 40, 255 - x * 255 // 400))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def photo_jpeg() -> bytes:
    rng = random.Random(7)
    image = Image.new("RGB", (400, 300))
    image.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(400 * 300)])
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()


def old_style_pdf(images: list[bytes], footer: str | None = None) -> bytes:
    """What ScoreCap used to write: raw, uncompressed image samples."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    y = 40
    for data in images:
        page.insert_image(pymupdf.Rect(40, y, 555, y + 120), stream=data)
        y += 130
    if footer:
        page.insert_text((280, 820), footer, fontsize=9)
    return doc.tobytes()  # no deflate: the 58 MB behaviour


def image_rects(data: bytes) -> list[tuple]:
    doc = pymupdf.open(stream=data, filetype="pdf")
    page = doc[0]
    rects = sorted(
        tuple(round(v, 1) for v in rect)
        for info in page.get_images(full=True)
        for rect in page.get_image_rects(info[0])
    )
    doc.close()
    return rects


def test_an_uncompressed_score_shrinks_a_lot():
    original = old_style_pdf([staff_png(i) for i in range(5)])
    result = optimize_pdf(original)
    assert result.after < result.before / 5, f"{result.before} -> {result.after}"
    assert result.images_rewritten == 5


def test_layout_and_page_count_are_untouched():
    original = old_style_pdf([staff_png(i) for i in range(5)], footer="1 von 1")
    result = optimize_pdf(original)
    assert image_rects(result.data) == image_rects(original)
    doc = pymupdf.open(stream=result.data, filetype="pdf")
    try:
        assert doc.page_count == 1
        assert "1 von 1" in doc[0].get_text()
    finally:
        doc.close()


def test_black_and_white_images_become_grey():
    result = optimize_pdf(old_style_pdf([staff_png(1)]))
    doc = pymupdf.open(stream=result.data, filetype="pdf")
    try:
        xref = doc[0].get_images(full=True)[0][0]
        assert pymupdf.Pixmap(doc, xref).n == 1
    finally:
        doc.close()


def test_colour_images_keep_their_colour():
    result = optimize_pdf(old_style_pdf([colour_png()]))
    doc = pymupdf.open(stream=result.data, filetype="pdf")
    try:
        xref = doc[0].get_images(full=True)[0][0]
        assert pymupdf.Pixmap(doc, xref).n == 3
    finally:
        doc.close()


def test_a_jpeg_photo_is_left_as_it_is():
    # Re-encoding a photo losslessly would make it bigger, not smaller.
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(pymupdf.Rect(40, 40, 440, 340), stream=photo_jpeg())
    original = doc.tobytes(deflate=True, garbage=3)
    result = optimize_pdf(original)
    out = pymupdf.open(stream=result.data, filetype="pdf")
    try:
        assert out[0].get_images(full=True)[0][8] == "DCTDecode"
    finally:
        out.close()
    assert result.after <= result.before


def test_the_result_is_never_bigger_than_the_input():
    once = optimize_pdf(old_style_pdf([staff_png(i) for i in range(3)])).data
    twice = optimize_pdf(once)
    assert twice.after <= twice.before
    assert len(twice.data) == twice.after


def test_something_that_is_not_a_pdf_is_rejected():
    with pytest.raises(ValueError):
        optimize_pdf(b"this is not a pdf")
