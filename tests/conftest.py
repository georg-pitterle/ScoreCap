import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(autouse=True)
def _never_block_on_unsaved_changes(monkeypatch):
    """Closing a window with captures would ask to save and wait forever.

    Tests that are about that question patch _ask_save_changes themselves.
    """
    monkeypatch.setattr(
        "scorecap.app.MainWindow._ask_save_changes", lambda self: "discard"
    )


@pytest.fixture(autouse=True)
def _private_settings_store(monkeypatch, tmp_path):
    """Windows opened in tests must not read or write the user's registry."""
    from PySide6.QtCore import QSettings

    path = str(tmp_path / "scorecap-settings.ini")
    monkeypatch.setattr(
        "scorecap.app.settings_store", lambda: QSettings(path, QSettings.IniFormat)
    )
