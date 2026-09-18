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
    assert "1 file missing" in window.status.text()


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


def arrow_system(tmp_path: Path) -> Shot:
    from PIL import ImageDraw

    image = Image.new("L", (1000, 260), 255)
    draw = ImageDraw.Draw(image)
    # Proportions of the real Perseus capture: the arrow takes the last
    # 2.5 % of the width, which lands about 5 mm into the margin.
    for line in range(5):
        draw.line([10, 40 + line * 12, 972, 40 + line * 12], fill=0, width=2)
    draw.line([978, 64, 996, 40], fill=0, width=2)  # the divisi arrow
    draw.line([978, 64, 996, 88], fill=0, width=2)
    path = tmp_path / "arrow.png"
    image.save(path)
    return Shot(path=path, width=1000, height=260)


def image_right_edge(pdf_bytes: bytes) -> float:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(0)
        xref = page.get_images(full=True)[0][0]
        return page.get_image_rects(xref)[0].x1
    finally:
        doc.close()


def test_a_divisi_arrow_hangs_into_the_margin(tmp_path, qapp):
    from dataclasses import replace

    from scorecap.app import MainWindow

    window = MainWindow()
    window.settings = replace(window.settings, align_staff_ends=True)
    window.add_shot(arrow_system(tmp_path))
    margin = window.settings.content_x_pt + window.settings.content_width_pt
    assert image_right_edge(window.pdf_bytes) > margin + 1


def test_flush_ends_can_be_switched_off(tmp_path, qapp):
    from dataclasses import replace

    from scorecap.app import MainWindow

    window = MainWindow()
    window.settings = replace(window.settings, align_staff_ends=False)
    window.add_shot(arrow_system(tmp_path))
    margin = window.settings.content_x_pt + window.settings.content_width_pt
    assert image_right_edge(window.pdf_bytes) == pytest.approx(margin, abs=0.5)


def test_double_clicking_a_shot_opens_the_crop_dialog_for_it(tmp_path, qapp, monkeypatch):
    import scorecap.app as app_module
    from scorecap.app import MainWindow

    opened = []

    class FakeDialog:
        def __init__(self, shot, parent, palette):
            opened.append(shot)
            self.crop = (0, 0, 500, 250)

        def exec(self):
            return True

    monkeypatch.setattr(app_module, "CropDialog", FakeDialog)
    window = MainWindow()
    window.add_shot(make_shot(tmp_path, "a.png"))
    window.add_shot(make_shot(tmp_path, "b.png"))
    window.shot_list.itemDoubleClicked.emit(window.shot_list.item(1))
    assert [s.path.name for s in opened] == ["b.png"]
    assert window.document.shots[1].crop == (0, 0, 500, 250)
    assert window.shot_list.currentRow() == 1


def test_a_missing_file_does_not_open_the_crop_dialog(tmp_path, qapp, monkeypatch):
    import scorecap.app as app_module
    from scorecap.app import MainWindow

    monkeypatch.setattr(app_module, "CropDialog", lambda *a: pytest.fail("opened"))
    window = MainWindow()
    shot = make_shot(tmp_path, "a.png")
    window.add_shot(shot)
    shot.path.unlink()
    window.rebuild()
    window.shot_list.itemDoubleClicked.emit(window.shot_list.item(0))
