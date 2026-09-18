"""Interface language, the Qt way.

Texts in the code are English and marked with tr() or
QCoreApplication.translate(). `pyside6-lupdate` collects them into
translations/scorecap_<lang>.ts, which Qt Linguist edits, and
`pyside6-lrelease` compiles those into the .qm files loaded here - see
tools/update_translations.py.

Which language is shown is Qt's choice as well: QTranslator.load() walks the
languages the user prefers in Windows, in order, and takes the first one a
translation exists for. The settings can pin one instead.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"

# Offered in the settings, each under its own name. "" follows Windows.
LANGUAGES = {"de": "Deutsch", "en": "English"}


def locale_for(language: str) -> QLocale:
    return QLocale(language) if language in LANGUAGES else QLocale.system()


def install(app: QCoreApplication, language: str = "") -> list[QTranslator]:
    """Load ScoreCap's and Qt's own translations for `language`.

    Qt's translation covers what Qt draws itself: standard dialog buttons,
    shortcut names such as Strg+O. Numbers follow the same locale.
    """
    locale = locale_for(language)
    QLocale.setDefault(locale)
    installed = []
    for name, folder in (
        ("scorecap", str(TRANSLATIONS_DIR)),
        ("qtbase", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)),
    ):
        translator = QTranslator(app)
        if translator.load(locale, name, "_", folder):
            app.installTranslator(translator)
            installed.append(translator)
    return installed
