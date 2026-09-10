from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from scorecap.model import Shot


def make_shot(tmp_path: Path, name: str, width: int = 1000, height: int = 500) -> Shot:
    path = tmp_path / name
    Image.new("RGB", (width, height), (10, 120, 200)).save(path)
    return Shot(path=path, width=width, height=height)


def test_usable_shots_reports_missing_files(tmp_path):
    from scorecap.app import usable_shots

    present = make_shot(tmp_path, "a.png")
    missing = Shot(path=tmp_path / "gone.png", width=100, height=50)
    usable, missing_indexes = usable_shots([present, missing, present])
    assert [s.path.name for s in usable] == ["a.png", "a.png"]
    assert missing_indexes == [1]


def test_window_rebuilds_pdf_when_shots_are_added(tmp_path, qapp):
    from scorecap.app import MainWindow

    window = MainWindow()
    assert window.pdf_bytes == b""
    window.add_shot(make_shot(tmp_path, "a.png"))
    window.add_shot(make_shot(tmp_path, "b.png"))
    doc = pymupdf.open(stream=window.pdf_bytes, filetype="pdf")
    try:
        assert doc.page_count == 1
    finally:
        doc.close()
    assert window.preview.page_count == 1
    assert window.shot_list.count() == 2


def test_export_writes_the_same_bytes(tmp_path, qapp):
    from scorecap.app import MainWindow

    window = MainWindow()
    window.add_shot(make_shot(tmp_path, "a.png"))
    target = tmp_path / "out.pdf"
    window.export_to(target)
    assert target.read_bytes() == window.pdf_bytes
    doc = pymupdf.open(str(target))
    try:
        assert doc.page_count == 1
    finally:
        doc.close()


def test_export_reports_write_errors(tmp_path, qapp):
    from scorecap.app import MainWindow

    window = MainWindow()
    window.add_shot(make_shot(tmp_path, "a.png"))
    with pytest.raises(OSError):
        window.export_to(tmp_path / "missing-dir" / "sub" / "out.pdf")


def test_missing_files_are_skipped_in_the_layout(tmp_path, qapp):
    from scorecap.app import MainWindow

    window = MainWindow()
    window.add_shot(make_shot(tmp_path, "a.png"))
    window.add_shot(Shot(path=tmp_path / "gone.png", width=1000, height=500))
    window.rebuild()
    doc = pymupdf.open(stream=window.pdf_bytes, filetype="pdf")
    try:
        assert len(doc.load_page(0).get_images(full=True)) == 1
    finally:
        doc.close()
    assert "fehlen" in window.status.text()


def test_undo_restores_a_removed_shot(tmp_path, qapp):
    from scorecap.app import MainWindow

    window = MainWindow()
    window.add_shot(make_shot(tmp_path, "a.png"))
    window.add_shot(make_shot(tmp_path, "b.png"))
    window.document.remove(1)
    window.rebuild()
    assert len(window.document.shots) == 1
    window.undo()
    assert len(window.document.shots) == 2
    assert window.shot_list.count() == 2
