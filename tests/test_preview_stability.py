"""The fitted preview must settle instead of chasing its own scrollbar."""

import time

import pytest
from PIL import Image

from scorecap import preview as preview_module
from scorecap.layout import paginate
from scorecap.model import Shot
from scorecap.pdf import build
from scorecap.settings import Settings


def tall_pdf(tmp_path, count: int = 10) -> bytes:
    settings = Settings()
    shots = []
    for index in range(count):
        path = tmp_path / f"{index}.png"
        Image.new("RGB", (1500, 220), (240, 240, 240)).save(path)
        shots.append(Shot(path=path, width=1500, height=220))
    pages = paginate([s.effective_size for s in shots], settings)
    return build(shots, pages, settings)


@pytest.fixture()
def counted_renders(monkeypatch):
    calls: list[float] = []
    original = preview_module.render_pages

    def counting(pdf_bytes, zoom=1.0):
        calls.append(zoom)
        return original(pdf_bytes, zoom)

    monkeypatch.setattr(preview_module, "render_pages", counting)
    return calls


def test_showing_a_document_settles_instead_of_re_rendering_forever(
    qapp, tmp_path, counted_renders
):
    widget = preview_module.PreviewWidget()
    widget.resize(900, 620)
    widget.show()
    widget.set_pdf(tall_pdf(tmp_path))

    deadline = time.perf_counter() + 1.0
    while time.perf_counter() < deadline:
        qapp.processEvents()

    widget.close()
    # One render for the document, plus a little slack for real layout passes.
    assert len(counted_renders) <= 3, f"rendered {len(counted_renders)} times"


def test_fit_zoom_ignores_whether_a_scrollbar_is_showing(qapp, tmp_path):
    widget = preview_module.PreviewWidget()
    widget.resize(900, 620)
    widget.show()

    widget.set_pdf(tall_pdf(tmp_path, count=10))  # tall: needs a scrollbar
    with_bar = widget.zoom
    widget.set_pdf(tall_pdf(tmp_path, count=1))  # short: fits without one
    without_bar = widget.zoom

    widget.close()
    assert with_bar == pytest.approx(without_bar)


def pump(qapp, ms: int) -> None:
    deadline = time.perf_counter() + ms / 1000
    while time.perf_counter() < deadline:
        qapp.processEvents()
        time.sleep(0.005)


def test_dragging_the_width_renders_once_after_the_drag_not_per_step(
    qapp, tmp_path, counted_renders
):
    widget = preview_module.PreviewWidget()
    widget.resize(1100, 700)
    widget.show()
    widget.set_pdf(tall_pdf(tmp_path, count=6))
    pump(qapp, 300)
    counted_renders.clear()

    for width in range(1100, 850, -5):  # a mouse drag: fifty resize events
        widget.resize(width, 700)
        qapp.processEvents()
    pump(qapp, 600)

    widget.close()
    assert len(counted_renders) <= 2, f"rendered {len(counted_renders)} times"


def test_a_fitted_page_follows_the_final_width_after_the_drag(qapp, tmp_path):
    widget = preview_module.PreviewWidget()
    widget.resize(1100, 700)
    widget.show()
    widget.set_pdf(tall_pdf(tmp_path, count=2))
    pump(qapp, 300)

    widget.resize(800, 700)
    pump(qapp, 600)

    expected = preview_module.fit_zoom(widget.width() - 2 * widget.frameWidth())
    widget.close()
    assert widget.zoom == pytest.approx(expected, abs=0.011)


def test_rebuilding_keeps_the_page_widgets_instead_of_blanking_the_canvas(
    qapp, tmp_path
):
    # Deleting and recreating the pages paints at least one empty frame, which
    # is the flicker. Same number of pages: the same widgets, new pixmaps.
    widget = preview_module.PreviewWidget()
    widget.resize(1000, 700)
    widget.show()
    widget.set_pdf(tall_pdf(tmp_path, count=6))
    before = [id(page) for page in widget.page_views()]

    widget.set_zoom(0.8)

    after = [id(page) for page in widget.page_views()]
    widget.close()
    assert before and before == after


def test_page_widgets_follow_a_changing_page_count(qapp, tmp_path):
    widget = preview_module.PreviewWidget()
    widget.resize(1000, 700)
    widget.show()
    widget.set_pdf(tall_pdf(tmp_path, count=12))
    many = widget.page_count
    widget.set_pdf(tall_pdf(tmp_path, count=1))
    widget.close()
    assert many > 1
    assert widget.page_count == 1
    assert len(widget.page_views()) == 1
