"""The interface as a German- and as an English-speaking user sees it."""

from PySide6.QtCore import QLocale

from scorecap import i18n
from scorecap.scan import ImportResult


def test_the_interface_speaks_german(german, qapp):
    from scorecap.app import MainWindow

    window = MainWindow()  # texts are set when a window is built
    try:
        assert window.capture_button.text() == "Aufnahme vorbereiten"
        # Qt's own translation names the shortcut the German way.
        assert "Strg+O" in window.open_button.toolTip()
        summary = window._import_summary(ImportResult([object()] * 3, 1, [], [], []))
        assert summary == "3 Systeme aus 1 Seite importiert"
    finally:
        window.close()


def test_english_plurals_read_naturally(qapp):
    from scorecap.app import MainWindow

    window = MainWindow()
    try:
        assert window._import_summary(ImportResult([object()], 1, [], [], [])) == (
            "1 system from 1 page imported"
        )
        assert window._import_summary(ImportResult([object()] * 2, 3, [], [], [])) == (
            "2 systems from 3 pages imported"
        )
    finally:
        window.close()


def test_a_pinned_language_overrides_windows():
    assert i18n.locale_for("de").language() == QLocale.Language.German
    assert i18n.locale_for("en").language() == QLocale.Language.English
    assert i18n.locale_for("").name() == QLocale.system().name()
    assert i18n.locale_for("klingon").name() == QLocale.system().name()
