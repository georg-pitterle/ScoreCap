"""Importing scans from the window: in the background, as one undo step."""

from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox

from scorecap.project import load_project
from tests.test_scan import page


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
    assert "3 Systeme aus 1 Seite" in window.status.text()
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
