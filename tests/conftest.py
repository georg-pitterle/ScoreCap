import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(autouse=True)
def _never_block_on_unsaved_changes(monkeypatch):
    """Closing a window with captures would ask to save and wait forever.

    Tests that are about that question patch ask_save_changes themselves.
    """
    monkeypatch.setattr("scorecap.app.ask_save_changes", lambda parent: "discard")


@pytest.fixture(autouse=True)
def _private_settings_store(monkeypatch, tmp_path):
    """Windows opened in tests must not read or write the user's registry."""
    from PySide6.QtCore import QSettings

    path = str(tmp_path / "scorecap-settings.ini")
    monkeypatch.setattr(
        "scorecap.app.settings_store", lambda: QSettings(path, QSettings.IniFormat)
    )


def _install(language):
    from PySide6.QtCore import QLocale
    from PySide6.QtWidgets import QApplication

    from scorecap import i18n

    app = QApplication.instance() or QApplication([])
    translators = i18n.install(app, language)
    yield
    for translator in translators:
        app.removeTranslator(translator)
    QLocale.setDefault(QLocale(QLocale.Language.English))


@pytest.fixture(autouse=True)
def _english(qapp):
    """Tests see the interface as an English-speaking user does."""
    yield from _install("en")


@pytest.fixture()
def german(_english):
    """The interface as a German-speaking user sees it."""
    yield from _install("de")
