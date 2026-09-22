"""Importing scans from the window: in the background, as one undo step."""

from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox

from scorecap.project import load_project
from tests.test_scan import horizontal_line_sharpness, page


@pytest.fixture()
def window(qapp):
    from scorecap.app import MainWindow

    win = MainWindow()
    win.show()
    yield win
    win.close()


def scan(tmp_path: Path, systems: list[int], name: str = "scan.png") -> Path:
    image, _ = page(systems)
    path = tmp_path / name
    image.rotate(0.8, Image.BICUBIC, fillcolor=230).save(path)
    return path


def test_scan_files_keeps_only_readable_suffixes():
    from scorecap.app import scan_files

    paths = [Path("a.PDF"), Path("b.jpg"), Path("c.scorecap"), Path("d.txt")]
    assert scan_files(paths) == [Path("a.PDF"), Path("b.jpg")]


def test_importing_a_scan_adds_one_shot_per_system(window, tmp_path, qtbot):
    window.import_files([scan(tmp_path, [1, 2, 1])])
    assert window.is_importing
    qtbot.waitUntil(lambda: not window.is_importing, timeout=30_000)
    assert len(window.document.shots) == 3
    assert window.shot_list.count() == 3
    assert window.pdf_bytes
    assert "3 systems from 1 page imported" in window.status.text()
    assert window.scan_button.isEnabled()


def test_one_undo_takes_back_the_whole_import(window, tmp_path, qtbot):
    window.import_files([scan(tmp_path, [1, 1])])
    qtbot.waitUntil(lambda: not window.is_importing, timeout=30_000)
    window.undo()
    assert window.document.shots == []


def test_unreadable_files_are_reported(window, tmp_path, qtbot, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"no pdf")
    window.import_files([broken, scan(tmp_path, [1])])
    qtbot.waitUntil(lambda: not window.is_importing, timeout=30_000)
    assert len(window.document.shots) == 1
    assert warnings and "broken.pdf" in warnings[0]


def test_imported_systems_survive_save_and_open(window, tmp_path, qtbot):
    window.import_files([scan(tmp_path, [1, 1])])
    qtbot.waitUntil(lambda: not window.is_importing, timeout=30_000)
    target = tmp_path / "noten.scorecap"
    window.save_to(target)
    loaded = load_project(target, tmp_path / "reopened")
    assert [s.crop for s in loaded] == [s.crop for s in window.document.shots]


def kept_part(shot):
    """What of a capture the export would print."""
    with Image.open(shot.path) as image:
        return image.crop(shot.crop or (0, 0, shot.width, shot.height))


def correct_on_the_page(window, qtbot, tmp_path, monkeypatch):
    """Import two systems, then crop the first one over both on the page."""
    from scorecap.cropdialog import CropDialog

    window.import_files([scan(tmp_path, [1, 1])])
    qtbot.waitUntil(lambda: not window.is_importing, timeout=30_000)

    def take_the_whole_page(dialog):
        dialog.show_page()
        whole = dialog.shot
        dialog._canvas._crop = (0, 0, whole.width, whole.height)
        return True

    monkeypatch.setattr(CropDialog, "exec", take_the_whole_page)
    window.shot_list.setCurrentRow(0)
    window.edit_selected()


def test_a_system_cut_apart_can_be_taken_in_again(
    window, tmp_path, qtbot, monkeypatch
):
    correct_on_the_page(window, qtbot, tmp_path, monkeypatch)
    corrected, untouched = window.document.shots  # the second one is the user's to delete
    assert horizontal_line_sharpness(kept_part(corrected)) >= 2 * horizontal_line_sharpness(
        kept_part(untouched)
    )


def test_undo_puts_the_cut_system_back(window, tmp_path, qtbot, monkeypatch):
    window.import_files([scan(tmp_path, [1, 1])])
    qtbot.waitUntil(lambda: not window.is_importing, timeout=30_000)
    was = window.document.shots[0]
    correct_on_the_page(window, qtbot, tmp_path, monkeypatch)
    window.undo()
    assert window.document.shots[0] == was


def test_a_reopened_project_has_no_page_to_go_back_to(
    window, tmp_path, qtbot, monkeypatch
):
    from scorecap.cropdialog import CropDialog

    window.import_files([scan(tmp_path, [1, 1])])
    qtbot.waitUntil(lambda: not window.is_importing, timeout=30_000)
    target = tmp_path / "noten.scorecap"
    window.save_to(target)
    window.load_from(target)
    offered = []
    monkeypatch.setattr(
        CropDialog,
        "exec",
        lambda dialog: offered.append(dialog.page_button.isEnabled()),
    )
    window.shot_list.setCurrentRow(0)
    window.edit_selected()
    assert offered == [False]
