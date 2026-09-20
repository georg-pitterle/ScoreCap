"""What the window does with a hotkey it cannot have."""

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QMessageBox


@pytest.fixture()
def window(qapp):
    from scorecap.app import MainWindow

    win = MainWindow()
    yield win
    win.close()


def test_a_hotkey_that_is_no_hotkey_still_lets_the_window_open(
    window, qapp, monkeypatch
):
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda parent, title, text: warnings.append(text)
    )
    window.settings = replace(window.settings, hotkey="F5")
    window.install_hotkey(qapp)
    assert warnings, "the user is left without a hotkey and is not told"
    assert "F5" in warnings[0]


def test_a_hotkey_that_is_no_hotkey_cannot_be_saved_in_the_settings(
    window, monkeypatch
):
    from scorecap.settingsdialog import SettingsDialog

    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda parent, title, text: warnings.append(text)
    )
    dialog = SettingsDialog(window.settings, window)
    dialog._hotkey.setText("F5")
    dialog.accept()
    assert dialog.result() == 0, "an unusable hotkey would break the next start"
    assert warnings

    dialog._hotkey.setText("Ctrl+Alt+M")
    dialog.accept()
    assert dialog.settings.hotkey == "Ctrl+Alt+M"


def test_the_empty_state_names_the_hotkey_in_force(window, monkeypatch):
    from scorecap.settingsdialog import SettingsDialog

    assert window.settings.hotkey in window.empty_state.text()

    def edited(dialog_settings, parent):
        dialog = SettingsDialog(dialog_settings, parent)
        dialog._hotkey.setText("Ctrl+Alt+M")
        return dialog

    monkeypatch.setattr("scorecap.app.SettingsDialog", edited)
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: 1)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    window.edit_settings()
    assert "Ctrl+Alt+M" in window.empty_state.text()


def test_the_hotkey_is_ignored_while_a_dialog_is_waiting(window, qapp):
    from PySide6.QtWidgets import QDialog

    dialog = QDialog(window)
    dialog.setModal(True)
    dialog.show()
    qapp.processEvents()
    try:
        window.begin_capture()  # what the hotkey does
        assert not window._overlay.isVisible()
        assert window.is_armed is False
    finally:
        dialog.done(0)
