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
