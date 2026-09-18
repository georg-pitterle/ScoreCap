from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from scorecap.layout import paginate
from scorecap.model import Shot
from scorecap.pdf import build
from scorecap.settings import A4_HEIGHT_PT, A4_WIDTH_PT, Settings


def make_png(tmp_path: Path, name: str, width: int, height: int) -> Shot:
    path = tmp_path / name
    Image.new("RGB", (width, height), (30, 60, 90)).save(path)
    return Shot(path=path, width=width, height=height)


def test_builds_one_a4_page_per_layout_page(tmp_path):
    settings = Settings()
    shots = [make_png(tmp_path, f"{i}.png", 1000, 700) for i in range(5)]
    pages = paginate([s.effective_size for s in shots], settings)
    doc = pymupdf.open(stream=build(shots, pages, settings), filetype="pdf")
    try:
        assert doc.page_count == len(pages)
        first = doc.load_page(0)
        assert first.rect.width == pytest.approx(A4_WIDTH_PT, abs=0.5)
        assert first.rect.height == pytest.approx(A4_HEIGHT_PT, abs=0.5)
    finally:
        doc.close()


def test_images_land_on_their_layout_rectangles(tmp_path):
    settings = Settings(footer_enabled=False)
    shots = [make_png(tmp_path, f"{i}.png", 1000, 400) for i in range(2)]
    pages = paginate([s.effective_size for s in shots], settings)
    doc = pymupdf.open(stream=build(shots, pages, settings), filetype="pdf")
    try:
        page = doc.load_page(0)
        # Identical images share one xref, so collect unique rectangles.
        rects = sorted(
            {
                tuple(rect)
                for xref in {info[0] for info in page.get_images(full=True)}
                for rect in page.get_image_rects(xref)
            },
            key=lambda rect: rect[1],
        )
        assert len(rects) == 2
        for rect, placement in zip(rects, pages[0].placements):
            x0, y0, x1, y1 = rect
            assert x0 == pytest.approx(placement.x, abs=1.0)
            assert y0 == pytest.approx(placement.y, abs=1.0)
            assert x1 - x0 == pytest.approx(placement.w, abs=1.0)
            assert y1 - y0 == pytest.approx(placement.h, abs=1.0)
    finally:
        doc.close()


def test_footer_shows_page_of_total(tmp_path):
    settings = Settings()
    shots = [make_png(tmp_path, f"{i}.png", 1000, 900) for i in range(3)]
    pages = paginate([s.effective_size for s in shots], settings)
    doc = pymupdf.open(stream=build(shots, pages, settings), filetype="pdf")
    try:
        total = doc.page_count
        for number in range(total):
            assert f"{number + 1} von {total}" in doc.load_page(number).get_text()
    finally:
        doc.close()


def test_footer_can_be_switched_off(tmp_path):
    settings = Settings(footer_enabled=False)
    shots = [make_png(tmp_path, "a.png", 1000, 400)]
    pages = paginate([s.effective_size for s in shots], settings)
    doc = pymupdf.open(stream=build(shots, pages, settings), filetype="pdf")
    try:
        assert doc.load_page(0).get_text().strip() == ""
    finally:
        doc.close()


def test_crop_is_applied_to_the_embedded_image(tmp_path):
    settings = Settings(footer_enabled=False)
    shot = make_png(tmp_path, "a.png", 1000, 400)
    cropped = Shot(path=shot.path, width=1000, height=400, crop=(0, 0, 500, 200))
    pages = paginate([cropped.effective_size], settings)
    doc = pymupdf.open(stream=build([cropped], pages, settings), filetype="pdf")
    try:
        page = doc.load_page(0)
        xref = page.get_images(full=True)[0][0]
        info = doc.extract_image(xref)
        assert (info["width"], info["height"]) == (500, 200)
    finally:
        doc.close()


def test_empty_document_produces_no_bytes():
    # PyMuPDF refuses to serialise a zero-page document, so an empty
    # document is represented by empty bytes.
    assert build([], [], Settings()) == b""


def line_art(tmp_path: Path, name: str, seed: int = 0, width: int = 1200, height: int = 300) -> Shot:
    """Something shaped like a staff: black strokes on white.

    Every call must produce different pixels: PyMuPDF stores identical images
    only once, so ten copies of one image would measure as a single image.
    """
    from PIL import ImageDraw

    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for line in range(5):
        y = 80 + line * 22
        draw.line([20, y, width - 20, y], fill=(20, 20, 20), width=2)
    for step, x in enumerate(range(60 + seed * 7, width - 60, 70)):
        y = 90 + ((step * 5 + seed * 3) % 9) * 11
        draw.ellipse([x, y, x + 22, y + 16], fill=(0, 0, 0))
    path = tmp_path / name
    image.save(path)
    return Shot(path=path, width=width, height=height)


def test_images_are_stored_grey_and_compressed(tmp_path):
    settings = Settings(footer_enabled=False)
    shots = [line_art(tmp_path, "a.png")]
    pages = paginate([s.effective_size for s in shots], settings)
    doc = pymupdf.open(stream=build(shots, pages, settings), filetype="pdf")
    try:
        info = doc.load_page(0).get_images(full=True)[0]
        xref, image_filter = info[0], info[8]
        # One channel is what matters; PyMuPDF labels it ICCBased with a grey
        # profile rather than DeviceGray.
        assert pymupdf.Pixmap(doc, xref).n == 1
        assert image_filter == "FlateDecode", f"stored with filter {image_filter!r}"
    finally:
        doc.close()


def test_a_score_sized_document_stays_small(tmp_path):
    # Ten staves of 1200 x 300 were 10.8 MB as raw RGB samples.
    settings = Settings()
    shots = [line_art(tmp_path, f"{i}.png", seed=i) for i in range(10)]
    pages = paginate([s.effective_size for s in shots], settings)
    data = build(shots, pages, settings)
    assert len(data) < 1_000_000, f"{len(data) / 1e6:.1f} MB"
