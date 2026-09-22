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
    ready = usable_shots([present, missing, present])
    assert [s.path.name for s in ready.shots] == ["a.png", "a.png"]
    assert ready.rows == [0, 2]
    assert ready.missing == [1]


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


def test_double_clicking_a_shot_opens_the_edit_dialog_for_it(tmp_path, qapp, monkeypatch):
    import scorecap.app as app_module
    from scorecap.app import MainWindow

    opened = []

    class FakeDialog:
        def __init__(self, shot, parent, palette, source=None):
            opened.append(shot)
            self.shot = shot
            self.crop = (0, 0, 500, 250)
            self.erasures = ((10, 10, 40, 40),)

        def exec(self):
            return True

    monkeypatch.setattr(app_module, "CropDialog", FakeDialog)
    window = MainWindow()
    window.add_shot(make_shot(tmp_path, "a.png"))
    window.add_shot(make_shot(tmp_path, "b.png"))
    window.shot_list.itemDoubleClicked.emit(window.shot_list.item(1))
    assert [s.path.name for s in opened] == ["b.png"]
    assert window.document.shots[1].crop == (0, 0, 500, 250)
    assert window.document.shots[1].erasures == ((10, 10, 40, 40),)
    assert window.shot_list.currentRow() == 1


def test_a_missing_file_does_not_open_the_edit_dialog(tmp_path, qapp, monkeypatch):
    import scorecap.app as app_module
    from scorecap.app import MainWindow

    monkeypatch.setattr(app_module, "CropDialog", lambda *a: pytest.fail("opened"))
    window = MainWindow()
    shot = make_shot(tmp_path, "a.png")
    window.add_shot(shot)
    shot.path.unlink()
    window.rebuild()
    window.shot_list.itemDoubleClicked.emit(window.shot_list.item(0))


# --- clicking in the preview picks the capture out of the list ---------------


def _middle_of(window, position: int) -> tuple[int, float, float]:
    """Page number and point in PDF points at the centre of one placement."""
    for page_number, page in enumerate(window.pages):
        for placement in page.placements:
            if placement.index == position:
                return (
                    page_number,
                    placement.x + placement.w / 2,
                    placement.y + placement.h / 2,
                )
    raise AssertionError(f"capture {position} is on no page")


def test_clicking_a_capture_in_the_preview_selects_its_row(tmp_path, qapp):
    from scorecap.app import MainWindow

    window = MainWindow()
    for name in ("a.png", "b.png", "c.png"):
        window.add_shot(make_shot(tmp_path, name))
    window.shot_list.setCurrentRow(0)

    window.preview.clicked_at.emit(*_middle_of(window, 2))
    assert window.shot_list.currentRow() == 2


def test_clicking_beside_the_captures_keeps_the_selection(tmp_path, qapp):
    from scorecap.app import MainWindow

    window = MainWindow()
    window.add_shot(make_shot(tmp_path, "a.png"))
    window.shot_list.setCurrentRow(0)

    window.preview.clicked_at.emit(0, 2.0, 2.0)  # the paper margin
    assert window.shot_list.currentRow() == 0


def test_a_missing_file_does_not_shift_what_a_click_selects(tmp_path, qapp):
    """The preview leaves out captures whose file is gone; the list does not."""
    from scorecap.app import MainWindow

    window = MainWindow()
    window.add_shot(make_shot(tmp_path, "a.png"))
    window.add_shot(make_shot(tmp_path, "gone.png"))
    window.add_shot(make_shot(tmp_path, "c.png"))
    (tmp_path / "gone.png").unlink()
    window.rebuild()

    # The second capture the preview shows is the third row of the list.
    window.preview.clicked_at.emit(*_middle_of(window, 1))
    assert window.shot_list.currentRow() == 2


# --- erasing lets the crop close in ------------------------------------------


def page_with_a_number(tmp_path: Path) -> Shot:
    """A system in the middle, a page number in the top right corner."""
    from PIL import ImageDraw

    image = Image.new("RGB", (200, 100), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle([50, 40, 149, 59], fill=(0, 0, 0))
    draw.rectangle([180, 10, 194, 19], fill=(0, 0, 0))
    path = tmp_path / "page.png"
    image.save(path)
    return Shot(path=path, width=200, height=100, crop=(48, 8, 197, 62))


def _dialog_returning(crop, erasures):
    class FakeDialog:
        def __init__(self, shot, parent, palette, source=None):
            self.shot = shot
            self.crop = shot.crop if crop == "unchanged" else crop
            self.erasures = erasures

        def exec(self):
            return True

    return FakeDialog


def test_erasing_a_page_number_pulls_the_crop_in(tmp_path, qapp, monkeypatch):
    import scorecap.app as app_module
    from scorecap.app import MainWindow

    monkeypatch.setattr(
        app_module, "CropDialog", _dialog_returning("unchanged", ((178, 8, 197, 22),))
    )
    window = MainWindow()
    window.add_shot(page_with_a_number(tmp_path))
    window.shot_list.setCurrentRow(0)
    window.edit_selected()
    assert window.document.shots[0].crop == (48, 38, 152, 62)


def test_a_visit_without_erasing_leaves_the_crop_as_it_was_set(tmp_path, qapp, monkeypatch):
    import scorecap.app as app_module
    from scorecap.app import MainWindow

    monkeypatch.setattr(app_module, "CropDialog", _dialog_returning((10, 10, 190, 90), ()))
    window = MainWindow()
    window.add_shot(page_with_a_number(tmp_path))
    window.shot_list.setCurrentRow(0)
    window.edit_selected()
    assert window.document.shots[0].crop == (10, 10, 190, 90)


def test_closing_clears_the_session_folder_whatever_is_left_in_it(tmp_path, qapp):
    from scorecap.app import MainWindow

    window = MainWindow()
    session = window._temp_dir
    # A cancelled scan import may not have stopped writing yet.
    (session / "half-written.png.part").write_bytes(b"xx")
    window.close()
    assert not session.exists()
