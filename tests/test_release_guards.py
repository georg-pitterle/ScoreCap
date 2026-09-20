"""Checks on files rather than on behaviour.

Everything else in this folder asks what the app does. These four ask whether
the repository is fit to be released: a version that drifted apart, a text
without a German translation or a stale `.qm` all reach the user silently,
and none of them can be caught by running the app.
"""

import importlib.util
import re
import shutil
import tomllib
import xml.etree.ElementTree as ET  # our own .ts files, not untrusted input
from pathlib import Path

import pytest

from scorecap._version import __version__

ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS = ROOT / "scorecap" / "translations"
PLACEHOLDER = re.compile(r"\{\w+\}")


def _messages(ts: Path) -> list[tuple[str, str, ET.Element]]:
    return [
        (context.findtext("name"), message.findtext("source"), message)
        for context in ET.parse(ts).iter("context")
        for message in context.iter("message")
    ]


def test_pyproject_and_module_agree():
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert declared["project"]["version"] == __version__, (
        "pyproject.toml and scorecap/_version.py drifted apart; "
        "release-please must update both"
    )


@pytest.mark.parametrize("language", ["de", "en"])
def test_the_translation_files_list_every_text_in_the_code(language, tmp_path):
    """Run tools/update_translations.py after changing a text."""
    spec = importlib.util.spec_from_file_location(
        "update_translations", ROOT / "tools" / "update_translations.py"
    )
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    committed = TRANSLATIONS / f"scorecap_{language}.ts"
    fresh = tmp_path / committed.name
    shutil.copy(committed, fresh)
    tool.update(fresh)
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
