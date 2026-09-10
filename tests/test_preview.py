import pytest
from PIL import Image

from scorecap.layout import paginate
from scorecap.model import Shot
from scorecap.pdf import build
from scorecap.settings import A4_HEIGHT_PT, A4_WIDTH_PT, Settings


def make_pdf(tmp_path, count: int) -> tuple[bytes, int]:
    settings = Settings()
    shots = []
    for index in range(count):
        path = tmp_path / f"{index}.png"
        Image.new("RGB", (1000, 900), (200, 40, 40)).save(path)
        shots.append(Shot(path=path, width=1000, height=900))
    pages = paginate([s.effective_size for s in shots], settings)
    return build(shots, pages, settings), len(pages)


def test_render_pages_returns_one_image_per_page(tmp_path, qapp):
    from scorecap.preview import render_pages

    pdf_bytes, page_count = make_pdf(tmp_path, 4)
    images = render_pages(pdf_bytes, zoom=1.0)
    assert len(images) == page_count
    assert images[0].width() == pytest.approx(A4_WIDTH_PT, abs=2)
    assert images[0].height() == pytest.approx(A4_HEIGHT_PT, abs=2)
    assert not images[0].isNull()


def test_no_pdf_renders_nothing(qapp):
    from scorecap.preview import render_pages

    assert render_pages(b"", zoom=1.0) == []


def test_zoom_scales_the_rendered_image(tmp_path, qapp):
    from scorecap.preview import render_pages

    pdf_bytes, _ = make_pdf(tmp_path, 1)
    small = render_pages(pdf_bytes, zoom=1.0)[0]
    large = render_pages(pdf_bytes, zoom=2.0)[0]
    assert large.width() == pytest.approx(small.width() * 2, abs=3)


def test_preview_widget_reports_its_page_count(tmp_path, qapp):
    from scorecap.preview import PreviewWidget

    pdf_bytes, page_count = make_pdf(tmp_path, 4)
    widget = PreviewWidget()
    widget.set_pdf(pdf_bytes)
    assert widget.page_count == page_count
    widget.set_pdf(b"")
    assert widget.page_count == 0
