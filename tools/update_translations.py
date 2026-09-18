"""Refresh the translation sources from the code and compile them.

Run after changing any text marked with tr():

    .venv/Scripts/python.exe tools/update_translations.py

pyside6-lupdate adds new texts to scorecap/translations/scorecap_<lang>.ts and
drops ones that are gone; translate them in Qt Linguist
(.venv/Scripts/pyside6-linguist.exe), then run this again so
pyside6-lrelease compiles the .qm files the app loads. English is the
language of the code; its file only supplies the plural forms.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "scorecap"
TRANSLATIONS = PACKAGE / "translations"
LANGUAGES = ("de", "en")


def tool(name: str) -> str:
    """A PySide6 tool from the same environment as this Python."""
    folder = Path(sys.executable).parent
    candidates = [folder / "Scripts" / f"pyside6-{name}.exe"]  # a system Python
    candidates += [folder / f"pyside6-{name}.exe", folder / f"pyside6-{name}"]  # a venv
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    found = shutil.which(f"pyside6-{name}")
    if found is None:
        raise SystemExit(f"pyside6-{name} not found - install PySide6 first")
    return found


def sources() -> list[str]:
    return sorted(str(path.relative_to(ROOT)) for path in PACKAGE.glob("*.py"))


def update(ts: Path) -> None:
    language = ts.stem.split("_")[-1]
    subprocess.run(
        [
            tool("lupdate"),
            *sources(),
            "-source-language", "en",
            "-target-language", language,
            # Line numbers would change the file on every edit of the code.
            "-locations", "none",
            "-no-obsolete",
            "-ts", str(ts),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def release(ts: Path, qm: Path) -> None:
    subprocess.run(
        [tool("lrelease"), "-silent", str(ts), "-qm", str(qm)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def main() -> None:
    TRANSLATIONS.mkdir(exist_ok=True)
    for language in LANGUAGES:
        ts = TRANSLATIONS / f"scorecap_{language}.ts"
        update(ts)
        release(ts, ts.with_suffix(".qm"))
        print(f"{ts.relative_to(ROOT)} updated and compiled")


if __name__ == "__main__":
    main()
