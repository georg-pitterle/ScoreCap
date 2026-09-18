"""Saving and opening projects from the window, without losing anything."""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from PySide6.QtWidgets import QFileDialog, QMessageBox

from scorecap.model import Shot
from scorecap.updater import PendingUpdate


def capture(tmp_path: Path, name: str, seed: int = 0) -> Shot:
    image = Image.new("RGB", (800, 200), "white")
    draw = ImageDraw.Draw(image)
    for line in range(5):
        draw.line([10, 40 + line * 12, 790, 40 + line * 12], fill="black", width=2)
    draw.ellipse([60 + seed * 40, 60, 80 + seed * 40, 74], fill="black")
    path = tmp_path / name
    image.save(path)
    return Shot(path=path, width=800, height=200)


@pytest.fixture()
def window(qapp):
    from scorecap.app import MainWindow

    win = MainWindow()
    win.show()
    yield win
    win.close()


def test_a_new_window_has_nothing_to_save(window):
    assert window.is_modified is False
    assert "ScoreCap" in window.windowTitle()


def test_adding_a_capture_marks_the_window_modified(window, tmp_path):
    window.add_shot(capture(tmp_path, "a.png"))
    assert window.is_modified is True
    assert window.isWindowModified() is True


def test_save_and_open_round_trip(window, tmp_path, qapp):
    from scorecap.app import MainWindow

    for seed in range(3):
        window.add_shot(capture(tmp_path, f"{seed}.png", seed))
    project = tmp_path / "Perseus.scorecap"
    window.save_to(project)
    assert window.is_modified is False
    assert "Perseus" in window.windowTitle()

    other = MainWindow()
    try:
        other.load_from(project)
        assert len(other.document.shots) == 3
        assert other.preview.page_count == window.preview.page_count
        assert other.is_modified is False
        assert other.document.can_undo is False
    finally:
        other.close()


def test_undo_after_saving_counts_as_a_change(window, tmp_path):
    window.add_shot(capture(tmp_path, "a.png"))
    window.add_shot(capture(tmp_path, "b.png", 1))
    window.save_to(tmp_path / "p.scorecap")
    window.undo()
    assert window.is_modified is True


def test_save_without_a_file_asks_for_one_and_adds_the_suffix(window, tmp_path, monkeypatch):
    window.add_shot(capture(tmp_path, "a.png"))
    target = tmp_path / "Chorstueck"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    assert window.save() is True
    assert (tmp_path / "Chorstueck.scorecap").exists()


def test_cancelling_the_save_dialog_saves_nothing(window, tmp_path, monkeypatch):
    window.add_shot(capture(tmp_path, "a.png"))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    assert window.save() is False
    assert window.is_modified is True


def test_closing_with_unsaved_captures_can_be_cancelled(window, tmp_path, monkeypatch):
    window.add_shot(capture(tmp_path, "a.png"))
    monkeypatch.setattr(type(window), "_ask_save_changes", lambda self: "cancel")
    window.close()
    assert window.isVisible()
    monkeypatch.setattr(type(window), "_ask_save_changes", lambda self: "discard")


def test_closing_can_save_first(window, tmp_path, monkeypatch):
    window.add_shot(capture(tmp_path, "a.png"))
    project = tmp_path / "p.scorecap"
    window.save_to(project)
    window.add_shot(capture(tmp_path, "b.png", 1))
    monkeypatch.setattr(type(window), "_ask_save_changes", lambda self: "save")
    window.close()
    assert not window.isVisible()
    from scorecap.project import load_project

    assert len(load_project(project, tmp_path / "check")) == 2


def test_a_saved_window_closes_without_asking(window, tmp_path, monkeypatch):
    window.add_shot(capture(tmp_path, "a.png"))
    window.save_to(tmp_path / "p.scorecap")
    monkeypatch.setattr(
        type(window), "_ask_save_changes", lambda self: pytest.fail("asked needlessly")
    )
    window.close()
    assert not window.isVisible()


def test_opening_over_unsaved_work_can_be_cancelled(window, tmp_path, monkeypatch):
    window.add_shot(capture(tmp_path, "a.png"))
    monkeypatch.setattr(type(window), "_ask_save_changes", lambda self: "cancel")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: pytest.fail("opened anyway")
    )
    window.open_project()
    assert len(window.document.shots) == 1


def test_a_broken_project_is_reported_and_changes_nothing(window, tmp_path, monkeypatch):
    window.add_shot(capture(tmp_path, "a.png"))
    broken = tmp_path / "broken.scorecap"
    broken.write_bytes(b"nope")
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a))
    window.load_from(broken)
    assert shown
    assert len(window.document.shots) == 1


def test_restarting_for_an_update_offers_to_save_unsaved_work(window, tmp_path, monkeypatch):
    class Service:
        restarted = []

        def is_available(self):
            # The window's deferred update check may still fire later.
            return False

        def restart_into(self, update):
            self.restarted.append(update)
            return True

        def install_on_exit(self, update):
            return True

    window.updates = Service()
    update = PendingUpdate(version="9.9.9", raw=object())
    window._on_update_downloaded(update, True)
    window.add_shot(capture(tmp_path, "a.png"))

    monkeypatch.setattr(type(window), "_ask_save_changes", lambda self: "cancel")
    window.update_button.click()
    assert Service.restarted == []

    window.save_to(tmp_path / "p.scorecap")  # nothing left to lose
    monkeypatch.setattr(
        type(window), "_ask_save_changes", lambda self: pytest.fail("asked needlessly")
    )
    window.update_button.click()
    assert Service.restarted == [update]


def test_no_button_of_the_save_question_is_cut_off(window, qapp):
    box, _save, _discard = window._unsaved_changes_box()
    box.show()
    qapp.processEvents()
    try:
        for button in box.buttons():
            assert button.width() >= button.sizeHint().width(), button.text()
    finally:
        box.done(0)


def test_open_and_save_start_in_the_last_project_folder(window, tmp_path, monkeypatch):
    folder = tmp_path / "Chor"
    folder.mkdir()
    window.add_shot(capture(tmp_path, "a.png"))
    window.save_to(folder / "Stueck.scorecap")
    asked = []
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: asked.append(a[2]) or ("", "")
    )
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **k: asked.append(a[2]) or ("", "")
    )
    window._project_path = None  # a fresh document proposes the folder too
    window.save_as()
    window.open_project()
    assert Path(asked[0]).parent == folder
    assert Path(asked[1]) == folder


def test_the_last_folders_survive_a_restart(window, tmp_path, monkeypatch, qapp):
    from scorecap.app import MainWindow

    folder = tmp_path / "Scans"
    folder.mkdir()
    scan = folder / "seite.png"
    Image.new("L", (100, 100), 255).save(scan)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(scan)], ""))
    window.choose_scans()
    window.close()
    asked = []
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames", lambda *a, **k: asked.append(a[2]) or ([], "")
    )
    again = MainWindow()
    again.choose_scans()
    again.close()
    assert Path(asked[0]) == folder


def test_a_vanished_folder_is_not_proposed(window, tmp_path, monkeypatch):
    folder = tmp_path / "weg"
    folder.mkdir()
    window.add_shot(capture(tmp_path, "a.png"))
    window.save_to(folder / "x.scorecap")
    (folder / "x.scorecap").unlink()
    folder.rmdir()
    asked = []
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: asked.append(a[2]) or ("", "")
    )
    window.open_project()
    assert asked == [""]
