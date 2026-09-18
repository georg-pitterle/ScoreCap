"""'PDF verkleinern' writes a new file beside the original and says what it did."""

import io

import pymupdf
import pytest
from PIL import Image, ImageDraw


def raw_pdf(count: int = 3) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    for index in range(count):
        image = Image.new("RGB", (1000, 250), "white")
        draw = ImageDraw.Draw(image)
        for line in range(5):
            draw.line([10, 60 + line * 20, 990, 60 + line * 20], fill="black", width=2)
        draw.ellipse([100 + index * 37, 90, 124 + index * 37, 106], fill="black")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        page.insert_image(pymupdf.Rect(40, 40 + index * 120, 555, 150 + index * 120), stream=buffer.getvalue())
    return doc.tobytes()  # uncompressed, as ScoreCap used to write


@pytest.fixture()
def window(qapp):
    from scorecap.app import MainWindow

    win = MainWindow()
    yield win
    win.close()


def test_shrinking_writes_a_smaller_copy_and_keeps_the_original(window, tmp_path):
    source = tmp_path / "Perseus.pdf"
    source.write_bytes(raw_pdf())
    original = source.read_bytes()
    target = tmp_path / "Perseus-klein.pdf"

    result = window.shrink_pdf_file(source, target)

    assert source.read_bytes() == original
    assert target.stat().st_size == result.after < result.before
    assert "Perseus.pdf" in window.status.text()
    assert "MB" in window.status.text()


def test_an_already_compact_pdf_is_not_rewritten(window, tmp_path):
    source = tmp_path / "klein.pdf"
    doc = pymupdf.open()
    doc.new_page()
    source.write_bytes(doc.tobytes(garbage=4, deflate=True))
    target = tmp_path / "klein-klein.pdf"

    window.shrink_pdf_file(source, target)

    assert not target.exists()
    assert "bereits" in window.status.text()


def test_a_file_that_is_not_a_pdf_raises_a_readable_error(window, tmp_path):
    source = tmp_path / "notes.pdf"
    source.write_bytes(b"not a pdf")
    with pytest.raises(ValueError):
        window.shrink_pdf_file(source, tmp_path / "out.pdf")


def test_suggested_name_sits_beside_the_original(window, tmp_path):
    from scorecap.app import shrunk_name

    assert shrunk_name(tmp_path / "Perseus.pdf") == tmp_path / "Perseus-klein.pdf"


def test_the_toolbar_offers_the_action(window):
    assert window.shrink_button.text().startswith("PDF verkleinern")
