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
