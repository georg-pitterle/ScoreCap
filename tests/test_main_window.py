"""The main window as one screen: what fits, what is in reach, what it says."""

import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from scorecap import i18n, omr, reader
from scorecap.model import Shot
from scorecap.seriesbar import bar_position
from scorecap.theme import DARK, LIGHT


@pytest.fixture()
def window(qapp, qtbot):
    from scorecap.app import MainWindow

    win = MainWindow()
    win.show()
    qtbot.waitExposed(win)
    yield win
    win.close()


def add_shots(window, tmp_path, count=3):
    for index in range(count):
        path = tmp_path / f"{index}.png"
        image = Image.new("RGB", (1400, 300), "white")
        image.paste((0, 0, 0), (0, 100, 1400, 200))
        image.save(path)
        window.document.add(Shot(path=path, width=1400, height=300))
    window.rebuild()


def press(widget, key, modifiers=Qt.KeyboardModifier.NoModifier):
    widget.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, modifiers))


def row_words(window, row):
    return window.shot_list.item(row).data(Qt.ItemDataRole.AccessibleTextRole)


# --- the window fits the screen -----------------------------------------------


@pytest.mark.parametrize("language", ["de", "en"])
def test_the_window_fits_a_small_laptop_screen_in_either_language(language, qapp):
    from scorecap.app import MainWindow

    translators = i18n.install(qapp, language)
    window = MainWindow()
    try:
        assert window.minimumSizeHint().width() <= 1280
    finally:
        window.close()
        for translator in translators:
            qapp.removeTranslator(translator)


def test_a_long_path_in_the_status_line_does_not_widen_the_window(window):
    before = window.minimumSizeHint().width()
    window.status.setText("D:/" + "a very long folder name/" * 40 + "score.pdf")
    assert window.minimumSizeHint().width() == before


def test_a_cut_status_line_keeps_the_whole_text_in_its_tooltip(window):
    text = "D:/" + "a very long folder name/" * 40 + "score.pdf"
    window.status.setText(text)
    assert window.status.text() == text
    assert window.status.toolTip() == text
    assert window.status.shown_text() != text

    window.status.setText("3 captures")
    assert window.status.toolTip() == ""


# --- the capture series ---------------------------------------------------------


def test_arming_says_what_to_press_next(window):
    window.arm_capture()
    assert window._series_bar.isVisible()
    assert window.settings.hotkey in window._series_bar.hint


def test_the_series_bar_counts_the_captures(window):
    window.begin_capture()
    window._on_selected(QRect(0, 0, 120, 80))
    assert window._series_bar.title == "Capture 1"
    window._on_selected(QRect(0, 0, 120, 80))
    assert window._series_bar.title == "Capture 2"


def test_the_series_bar_never_takes_the_focus_from_the_browser(window):
    window.begin_capture()
    window._on_selected(QRect(0, 0, 120, 80))
    assert window._series_bar.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus


def test_the_series_bar_stays_out_of_the_next_capture(window):
    window.arm_capture()
    assert window._series_bar.isVisible()
    window.begin_capture()
    assert not window._series_bar.isVisible()


def test_a_slip_of_the_mouse_stays_in_the_series(window):
    window.begin_capture()
    window._on_selected(QRect(0, 0, 120, 80))
    window._overlay.missed.emit()
    assert window.is_armed
    assert window.isMinimized()
    assert "too small" in window._series_bar.hint
    assert len(window.document.shots) == 1


def test_undo_in_the_bar_takes_back_only_this_series(window, tmp_path):
    add_shots(window, tmp_path, count=2)
    window.begin_capture()
    window._on_selected(QRect(0, 0, 120, 80))
    window._series_bar.undo_button.click()
    assert len(window.document.shots) == 2
    assert not window._series_bar.undo_button.isEnabled()

    window._undo_in_series()
    assert len(window.document.shots) == 2


def test_done_in_the_bar_brings_the_window_back_on_the_newest_capture(
    window, tmp_path
):
    add_shots(window, tmp_path, count=1)
    window.begin_capture()
    window._on_selected(QRect(0, 0, 120, 80))
    window._series_bar.done_button.click()
    assert not window.isMinimized()
    assert not window._series_bar.isVisible()
    assert window.shot_list.currentRow() == 1


def test_the_bar_cannot_be_dragged_off_the_screen():
    screen = QRect(0, 0, 1000, 700)
    size = screen.size() / 4
    placed = bar_position(screen, size, screen.bottomRight())
    assert screen.contains(QRect(placed, size))


def test_a_new_bar_sits_low_and_centred_on_the_screen():
    screen = QRect(1920, 0, 1000, 700)
    size = screen.size() / 4
    placed = bar_position(screen, size, None)
    assert QRect(placed, size).center().x() == pytest.approx(screen.center().x(), abs=1)
    assert placed.y() > screen.center().y()


# --- exports -------------------------------------------------------------------


def test_an_empty_window_offers_nothing_to_export(window):
    assert not window.musicxml_button.isEnabled()
    assert not window.export_button.isEnabled()
    assert not window.export_action.isEnabled()


def test_a_missing_reader_is_named_before_the_file_dialog(window, tmp_path, monkeypatch):
    add_shots(window, tmp_path)
    asked, told = [], []

    def missing():
        raise omr.AudiverisMissing("not installed")

    monkeypatch.setattr(omr, "find_audiveris", missing)
    monkeypatch.setattr(
        "scorecap.app.QFileDialog.getSaveFileName",
        lambda *args: asked.append(args) or ("", ""),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args: told.append(args))
    window.export_musicxml("audiveris")
    assert told
    assert not asked


def test_a_missing_claude_is_named_before_the_file_dialog(window, tmp_path, monkeypatch):
    add_shots(window, tmp_path)
    asked, told = [], []

    def missing():
        raise reader.ClaudeMissing("not installed")

    monkeypatch.setattr(reader, "find_claude", missing)
    monkeypatch.setattr(
        "scorecap.app.QFileDialog.getSaveFileName",
        lambda *args: asked.append(args) or ("", ""),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args: told.append(args))
    window.export_musicxml("claude")
    assert told
    assert not asked


def waiting_audiveris(
    launcher, source, out_dir, progress=None, timeout=1800, cancelled=None
):
    while not cancelled():
        pass
    return "stopped"


def running_transcription(window, tmp_path, monkeypatch):
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    add_shots(window, tmp_path)
    window.export_musicxml_to(tmp_path / "out.musicxml", run=waiting_audiveris)


def test_a_running_transcription_can_be_cancelled(window, tmp_path, monkeypatch, qtbot):
    running_transcription(window, tmp_path, monkeypatch)
    assert window.cancel_button.isVisible()

    window.cancel_button.click()
    qtbot.waitUntil(lambda: not window.is_transcribing, timeout=5_000)

    assert not window.cancel_button.isVisible()
    assert "cancelled" in window.status.text()
    assert not (tmp_path / "out.musicxml").exists()
    assert window.musicxml_button.isEnabled()


def test_closing_during_a_transcription_can_be_refused(
    window, tmp_path, monkeypatch, qtbot
):
    running_transcription(window, tmp_path, monkeypatch)
    monkeypatch.setattr("scorecap.app.ask_stop_transcription", lambda parent: False)
    window.close()
    assert window.isVisible()

    window.cancel_transcription()
    qtbot.waitUntil(lambda: not window.is_transcribing, timeout=5_000)


def test_closing_stops_the_transcription_before_its_folder_goes(
    qapp, tmp_path, monkeypatch
):
    from scorecap.app import MainWindow

    window = MainWindow()
    running_transcription(window, tmp_path, monkeypatch)
    task = window._musicxml_task
    window.close()
    assert task.stopped.is_set()


def test_the_exported_file_stays_reported_and_can_be_opened(
    window, tmp_path, monkeypatch
):
    add_shots(window, tmp_path)
    target = tmp_path / "score.pdf"
    monkeypatch.setattr(
        "scorecap.app.QFileDialog.getSaveFileName", lambda *args: (str(target), "")
    )
    opened = []
    monkeypatch.setattr(
        "scorecap.app.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )

    window.export()
    window.rebuild()  # any later change to the captures

    assert "score.pdf" in window.status.text()
    window.result_button.click()
    assert opened == [target.as_posix()]


def test_a_pdf_held_open_elsewhere_is_explained_in_plain_words(
    window, tmp_path, monkeypatch
):
    add_shots(window, tmp_path)
    target = tmp_path / "score.pdf"
    monkeypatch.setattr(
        "scorecap.app.QFileDialog.getSaveFileName", lambda *args: (str(target), "")
    )

    def locked(path):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(window, "export_to", locked)
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: shown.append(args[2]))
    window.export()
    assert "score.pdf" in shown[0]
    assert "Errno" not in shown[0]
    assert "open" in shown[0]


# --- keyboard and screen readers -------------------------------------------------


@pytest.mark.parametrize(
    "button", ["capture_button", "open_button", "export_button", "edit_button"]
)
def test_a_focused_button_looks_different(window, tmp_path, button, qapp):
    add_shots(window, tmp_path)
    window.shot_list.setCurrentRow(0)
    target = getattr(window, button)

    window.setFocus()
    qapp.processEvents()
    plain = target.grab().toImage()

    target.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    assert target.hasFocus()
    assert target.grab().toImage() != plain


def test_every_icon_only_button_has_a_name(window):
    for button in (
        window.zoom_in_button,
        window.zoom_out_button,
        window.undo_button,
        window.recapture_button,
        window.edit_button,
        window.delete_button,
    ):
        assert button.accessibleName()


def test_a_list_row_has_words_for_a_screen_reader(window, tmp_path):
    add_shots(window, tmp_path)
    assert "Capture 2" in row_words(window, 1)
    assert "page 1" in row_words(window, 1)


def test_the_delete_key_deletes_the_selected_capture(window, tmp_path):
    add_shots(window, tmp_path)
    window.shot_list.setCurrentRow(1)
    press(window.shot_list, Qt.Key.Key_Delete)
    assert len(window.document.shots) == 2


def test_enter_opens_the_selected_capture_for_editing(window, tmp_path, monkeypatch):
    add_shots(window, tmp_path)
    window.shot_list.setCurrentRow(0)
    opened = []
    monkeypatch.setattr(
        "scorecap.app.CropDialog", lambda *a, **k: opened.append(a) or _Declined()
    )
    press(window.shot_list, Qt.Key.Key_Return)
    assert opened


class _Declined:
    mode = "crop"

    def exec(self):
        return False


def test_alt_and_the_arrows_reorder_and_keep_the_capture_selected(window, tmp_path):
    add_shots(window, tmp_path)
    first = window.document.shots[0]
    window.shot_list.setCurrentRow(0)
    press(window.shot_list, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    assert window.document.shots[1] == first
    assert window.shot_list.currentRow() == 1


def test_a_capture_cannot_be_moved_past_either_end(window, tmp_path):
    add_shots(window, tmp_path)
    before = window.document.shots
    window.shot_list.setCurrentRow(0)
    press(window.shot_list, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
    assert window.document.shots == before


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=["light", "dark"])
def test_the_main_button_stays_readable_in_both_themes(palette):
    def luminance(colour):
        channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [
            c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            for c in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    for background in (palette.accent, palette.accent_hover):
        lighter, darker = sorted(
            (luminance(background), luminance(palette.on_accent)), reverse=True
        )
        assert (lighter + 0.05) / (darker + 0.05) >= 4.5


# --- the list and the proof -----------------------------------------------------


def test_selecting_a_row_marks_the_capture_on_its_page(window, tmp_path):
    add_shots(window, tmp_path, count=3)
    window.shot_list.setCurrentRow(1)
    page, area = window.preview.marked_area()
    placement = window.pages[0].placements[1]
    assert page == 0
    assert area.y() == round(placement.y * window.preview.zoom)
    assert area.height() == round(placement.h * window.preview.zoom)


def test_the_mark_follows_the_zoom(window, tmp_path):
    add_shots(window, tmp_path)
    window.shot_list.setCurrentRow(0)
    _, before = window.preview.marked_area()
    window.zoom_in_button.click()
    _, after = window.preview.marked_area()
    assert after.width() > before.width()


def test_deleting_the_last_capture_clears_the_mark(window, tmp_path):
    add_shots(window, tmp_path, count=1)
    window.shot_list.setCurrentRow(0)
    window.delete_selected()
    assert window.preview.marked_area() is None


def test_an_empty_proof_shows_a_blank_sheet_that_says_how_to_begin(window, tmp_path):
    assert window.settings.hotkey in window.preview.blank_text
    assert not window._zoom_bar.isEnabled()

    add_shots(window, tmp_path, count=1)
    assert window._zoom_bar.isEnabled()
    assert window.preview.page_count == 1


def test_closing_during_a_series_leaves_no_bar_behind(qapp, tmp_path):
    from scorecap.app import MainWindow

    window = MainWindow()
    window.arm_capture()
    window.close()
    qapp.processEvents()
    visible = [w for w in QApplication.topLevelWidgets() if w.isVisible()]
    assert window._series_bar not in visible


# --- capturing the last one again -----------------------------------------------


def series_of(window, count):
    window.begin_capture()
    for _ in range(count):
        window._on_selected(QRect(0, 0, 120, 80))


def test_again_takes_the_last_capture_back_and_opens_the_overlay(window):
    series_of(window, 2)
    window._series_bar.retake_button.click()
    assert len(window.document.shots) == 1
    assert window._overlay.isVisible()
    assert window.is_armed
    assert window.isMinimized()


def test_the_series_runs_on_after_capturing_again(window):
    series_of(window, 2)
    window.retake_capture()
    window._on_selected(QRect(0, 0, 200, 100))
    window._on_selected(QRect(0, 0, 200, 100))
    assert len(window.document.shots) == 3
    assert window._series_bar.title == "Capture 3"


def test_again_never_reaches_past_the_start_of_the_series(window, tmp_path):
    add_shots(window, tmp_path, count=2)
    window.begin_capture()
    window.retake_capture()
    assert len(window.document.shots) == 2


def test_outside_a_series_the_retake_hotkey_does_nothing(window, tmp_path):
    add_shots(window, tmp_path, count=2)
    window.retake_capture()
    assert len(window.document.shots) == 2
    assert not window._overlay.isVisible()


def test_a_right_click_on_the_dimmed_screen_goes_back_to_the_last_one(window):
    series_of(window, 2)
    window.begin_capture()
    window._overlay.retake.emit()
    assert len(window.document.shots) == 1
    assert window._overlay.isVisible()


def test_the_retake_hotkey_is_held_only_during_a_series(window, monkeypatch):
    held = []
    monkeypatch.setattr(window._retake_hotkey, "register", held.append)
    monkeypatch.setattr(window._retake_hotkey, "unregister", lambda: held.clear())
    window._hotkeys_installed = True

    window.begin_capture()
    assert held == [window.settings.retake_hotkey]
    window.finish_capture()
    assert held == []


# --- redo -----------------------------------------------------------------------


def test_redo_brings_a_deleted_capture_back_out_again(window, tmp_path):
    add_shots(window, tmp_path)
    window.shot_list.setCurrentRow(0)
    window.delete_selected()
    window.undo_button.click()
    assert len(window.document.shots) == 3
    window.redo_button.click()
    assert len(window.document.shots) == 2


def test_undo_and_redo_are_only_offered_when_they_can_do_something(window, tmp_path):
    assert not window.undo_button.isEnabled()
    assert not window.redo_button.isEnabled()
    add_shots(window, tmp_path)
    assert window.undo_button.isEnabled()
    window.undo()
    assert window.redo_button.isEnabled()


# --- several captures at once ---------------------------------------------------


def select(window, *rows):
    window.shot_list.clearSelection()
    for row in rows:
        window.shot_list.item(row).setSelected(True)


def test_several_selected_captures_are_deleted_in_one_step(window, tmp_path):
    add_shots(window, tmp_path, count=4)
    select(window, 0, 2)
    window.delete_selected()
    assert len(window.document.shots) == 2
    window.undo()
    assert len(window.document.shots) == 4


def test_editing_and_recapturing_wait_for_a_single_selection(window, tmp_path):
    add_shots(window, tmp_path)
    select(window, 0, 1)
    assert not window.edit_button.isEnabled()
    assert not window.recapture_button.isEnabled()
    assert window.delete_button.isEnabled()

    window.recapture_selected()
    assert not window.is_armed


def test_alt_and_the_arrows_move_a_selected_block_and_keep_it_selected(
    window, tmp_path
):
    add_shots(window, tmp_path, count=4)
    moved = window.document.shots[:2]
    select(window, 0, 1)
    press(window.shot_list, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    assert window.document.shots[1:3] == moved
    assert window.shot_list.selected_rows() == [1, 2]


def test_a_rebuild_keeps_the_selection(window, tmp_path):
    add_shots(window, tmp_path, count=3)
    select(window, 0, 2)
    window.rebuild()
    assert window.shot_list.selected_rows() == [0, 2]


def test_dragging_several_rows_takes_one_undo_step(window, tmp_path, qtbot):
    from PySide6.QtCore import QModelIndex

    add_shots(window, tmp_path, count=4)
    before = window.document.shots
    model = window.shot_list.model()
    model.moveRows(QModelIndex(), 0, 1, QModelIndex(), 4)
    model.moveRows(QModelIndex(), 0, 1, QModelIndex(), 4)
    qtbot.waitUntil(lambda: window.document.shots != before, timeout=1_000)

    assert window.document.shots != before
    window.undo()
    assert window.document.shots == before
