"""The interface in German and English, through Qt's own translation tools."""

import importlib.util
import re
import shutil
import xml.etree.ElementTree as ET  # our own .ts files, not untrusted input
from pathlib import Path

import pytest
from PySide6.QtCore import QLocale

from scorecap import i18n
from scorecap.scan import ImportResult

ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS = ROOT / "scorecap" / "translations"
PLACEHOLDER = re.compile(r"\{\w+\}")


def _tool():
    spec = importlib.util.spec_from_file_location(
        "update_translations", ROOT / "tools" / "update_translations.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def window(qapp):
    from scorecap.app import MainWindow

    win = MainWindow()
    yield win
    win.close()


def _messages(ts: Path) -> list[tuple[str, str, ET.Element]]:
    return [
        (context.findtext("name"), message.findtext("source"), message)
        for context in ET.parse(ts).iter("context")
        for message in context.iter("message")
    ]


@pytest.mark.parametrize("language", ["de", "en"])
def test_the_translation_files_list_every_text_in_the_code(language, tmp_path):
    """Run tools/update_translations.py after changing a text."""
    committed = TRANSLATIONS / f"scorecap_{language}.ts"
    fresh = tmp_path / committed.name
    shutil.copy(committed, fresh)
    _tool().update(fresh)
    keys = lambda ts: sorted((context, source) for context, source, _ in _messages(ts))  # noqa: E731
    assert keys(fresh) == keys(committed)


@pytest.mark.parametrize("language", ["de", "en"])
def test_the_compiled_translations_match_their_sources(language, qapp):
    """A stale .qm would show old texts although the .ts is right."""
    from PySide6.QtCore import QTranslator

    translator = QTranslator()
    assert translator.load(str(TRANSLATIONS / f"scorecap_{language}.qm"))
    for context, source, message in _messages(TRANSLATIONS / f"scorecap_{language}.ts"):
        forms = [form.text for form in message.iter("numerusform")]
        if forms:
            for count, form in ((1, forms[0]), (2, forms[-1])):
                assert translator.translate(context, source, "", count) == form, source
        elif message.findtext("translation"):
            assert translator.translate(context, source) == message.findtext("translation")


def test_every_text_has_a_german_translation():
    unfinished = [
        message.findtext("source")
        for message in ET.parse(TRANSLATIONS / "scorecap_de.ts").iter("message")
        if message.find("translation").get("type") == "unfinished"
    ]
    assert unfinished == []


@pytest.mark.parametrize("language", ["de", "en"])
def test_translations_keep_their_placeholders(language):
    for message in ET.parse(TRANSLATIONS / f"scorecap_{language}.ts").iter("message"):
        source = message.findtext("source")
        translation = message.find("translation")
        forms = [form.text or "" for form in translation.iter("numerusform")]
        if not forms:
            if not translation.text:
                continue  # English: the source is the text
            forms = [translation.text]
        for form in forms:
            assert set(PLACEHOLDER.findall(form)) == set(PLACEHOLDER.findall(source)), source
            if message.get("numerus") == "yes":
                assert "%n" in form, source


def test_the_interface_speaks_german(window, german):
    from scorecap.app import MainWindow

    german_window = MainWindow()  # texts are set when a window is built
    try:
        assert german_window.capture_button.text() == "Aufnahme vorbereiten"
        # Qt's own translation names the shortcut the German way.
        assert "Strg+O" in german_window.open_button.toolTip()
        summary = german_window._import_summary(ImportResult([object()] * 3, 1, [], [], []))
        assert summary == "3 Systeme aus 1 Seite importiert"
    finally:
        german_window.close()


def test_english_plurals_read_naturally(window):
    assert window._import_summary(ImportResult([object()], 1, [], [], [])) == (
        "1 system from 1 page imported"
    )
    assert window._import_summary(ImportResult([object()] * 2, 3, [], [], [])) == (
        "2 systems from 3 pages imported"
    )


def test_a_pinned_language_overrides_windows():
    assert i18n.locale_for("de").language() == QLocale.Language.German
    assert i18n.locale_for("en").language() == QLocale.Language.English
    assert i18n.locale_for("").name() == QLocale.system().name()
    assert i18n.locale_for("klingon").name() == QLocale.system().name()
