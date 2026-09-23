# MusicXML-Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A capture set leaves ScoreCap as one MusicXML file, transcribed by an
Audiveris the user installed, so a voice can be played back for practice.

**Architecture:** A Qt-free `omr.py` finds Audiveris, runs it in batch over a
PDF ScoreCap renders for the purpose, glues the movements Audiveris writes into
one document, puts the missed octave clef right and writes the file atomically.
`tasks.py` runs that off the window like a scan import; `app.py` adds the
button, the file dialog and the message that explains a missing Audiveris.

**Tech Stack:** Python 3.11+, PySide6 (QtCore/QtGui/QtWidgets only), PyMuPDF,
Pillow, `xml.etree.ElementTree` and `zipfile` from the standard library,
Audiveris 5.x as an external program.

## Global Constraints

- Code, docstrings, comments and test names in English; `README.md` and
  everything under `docs/` in German. Every string the user reads goes through
  `self.tr(...)` or `QCoreApplication.translate("context", ...)`, and
  `.venv/Scripts/python.exe tools/update_translations.py` runs after any text
  change - otherwise `tests/test_release_guards.py` fails.
- `from __future__ import annotations` at the top of every module, relative
  imports inside the package, lines under 88 characters, `log =
  logging.getLogger(__name__)` per module.
- What can compute stays free of Qt: `omr.py` takes paths and returns paths.
- Data classes are frozen; invalid values raise `ValueError` in the
  constructor.
- Tests check behaviour, never construction: no colour values, no
  `isinstance`, no call counts, no reading of source. Test names are whole
  sentences about what the user experiences.
- **No test may start a JVM.** Audiveris is always injected as a callable.
- Run tests with `.venv/Scripts/python.exe -m pytest -q`; the suite must stay
  in the seconds.
- Commit messages follow Conventional Commits and name the benefit, not the
  change. Do not push.
- Do not touch `CHANGELOG.md` or the version: release-please owns both.

---

## File Structure

| File | Responsibility |
|---|---|
| `scorecap/omr.py` (new) | Find and run Audiveris, glue movements, fix the octave clef, write the file |
| `scorecap/tasks.py` | `MusicXmlSignals` and `MusicXmlExport`, the job off the window |
| `scorecap/app.py` | The button, the dialogs, the grey render handed to Audiveris |
| `tests/test_omr.py` (new) | Everything `omr.py` promises, with a stub Audiveris |
| `tests/test_musicxml_ui.py` (new) | What the user sees: the missing-Audiveris note, the written file |
| `docs/aufbau.md`, `README.md` | The new module, the new button |

---

### Task 1: Find Audiveris

**Files:**
- Create: `scorecap/omr.py`
- Test: `tests/test_omr.py`

**Interfaces:**
- Produces: `class AudiverisMissing(Exception)`, `DOWNLOAD_URL: str` and
  `find_audiveris() -> Path`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_omr.py`:

```python
"""Transcribing a score with Audiveris, without ever starting one."""

import pytest

from scorecap import omr


def test_a_missing_audiveris_is_reported_rather_than_guessed(monkeypatch, tmp_path):
    monkeypatch.delenv("AUDIVERIS_HOME", raising=False)
    monkeypatch.setattr(omr, "CANDIDATES", (tmp_path / "nowhere.exe",))

    with pytest.raises(omr.AudiverisMissing):
        omr.find_audiveris()


def test_an_audiveris_installed_elsewhere_is_found_through_the_environment(
    monkeypatch, tmp_path
):
    home = tmp_path / "Audiveris"
    home.mkdir()
    launcher = home / "Audiveris.exe"
    launcher.write_text("", encoding="utf-8")
    monkeypatch.setenv("AUDIVERIS_HOME", str(home))
    monkeypatch.setattr(omr, "CANDIDATES", ())

    assert omr.find_audiveris() == launcher
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_omr.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'scorecap.omr'`.

- [ ] **Step 3: Write the module**

Create `scorecap/omr.py`:

```python
"""Score images to MusicXML: Audiveris in, one playable file out."""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

DOWNLOAD_URL = "https://github.com/Audiveris/audiveris/releases"

CANDIDATES = (
    Path(r"C:\Program Files\Audiveris\Audiveris.exe"),
    Path(r"C:\Program Files (x86)\Audiveris\Audiveris.exe"),
    Path.home() / "AppData/Local/Programs/Audiveris/Audiveris.exe",
)
LAUNCHERS = ("Audiveris.exe", "bin/Audiveris.bat")


class AudiverisMissing(Exception):
    """Audiveris is not installed - the one error the user can act on."""


def find_audiveris() -> Path:
    """The Audiveris launcher, looked up afresh on every export.

    Looked up rather than remembered: someone who installs it while ScoreCap
    is open should not have to restart.
    """
    home = os.environ.get("AUDIVERIS_HOME")
    if home:
        for name in LAUNCHERS:
            launcher = Path(home) / name
            if launcher.exists():
                return launcher
    for candidate in CANDIDATES:
        if candidate.exists():
            return candidate
    raise AudiverisMissing("Audiveris is not installed")
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_omr.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scorecap/omr.py tests/test_omr.py
git commit -m "feat: find an installed Audiveris for transcribing"
```

---

### Task 2: Glue the movements into one score

**Files:**
- Modify: `scorecap/omr.py`
- Test: `tests/test_omr.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `read_score(path: Path) -> ElementTree.Element` (an `.mxl` or a
  plain `.musicxml`) and
  `glue(documents: Sequence[ElementTree.Element]) -> ElementTree.Element`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_omr.py`:

```python
from xml.etree import ElementTree


def score_xml(measures: int, pitch: str = "C", octave: str = "4") -> str:
    bars = "".join(
        f'<measure number="{number}"><note><pitch><step>{pitch}</step>'
        f"<octave>{octave}</octave></pitch><duration>4</duration></note></measure>"
        for number in range(1, measures + 1)
    )
    return (
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        "<part-name>Soprano</part-name></score-part></part-list>"
        f'<part id="P1">{bars}</part></score-partwise>'
    )


def test_two_movements_become_one_score_with_every_bar_of_both():
    first = ElementTree.fromstring(score_xml(2))
    second = ElementTree.fromstring(score_xml(3))

    glued = omr.glue([first, second])

    measures = glued.find(".//part").findall("measure")
    assert len(measures) == 5
    assert [m.get("number") for m in measures] == ["1", "2", "3", "4", "5"]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_omr.py -q`
Expected: FAIL, `AttributeError: module 'scorecap.omr' has no attribute 'glue'`.

- [ ] **Step 3: Write the code**

Add to `scorecap/omr.py`, with `import zipfile`, `from typing import Sequence`
and `from xml.etree import ElementTree` at the top:

```python
def read_score(path: Path) -> ElementTree.Element:
    """The score in a MusicXML file, packed (.mxl) or plain."""
    if path.suffix.lower() != ".mxl":
        return ElementTree.parse(path).getroot()
    with zipfile.ZipFile(path) as archive:
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//rootfile")
        name = rootfile.get("full-path") if rootfile is not None else "score.xml"
        return ElementTree.fromstring(archive.read(name))


def glue(documents: Sequence[ElementTree.Element]) -> ElementTree.Element:
    """One score out of the movements Audiveris split a book into.

    Audiveris starts a new movement wherever it sees a new beginning, and a
    heft of several pieces comes back in pieces. The user asked for one
    file, so the parts are appended in order and the bars renumbered - two
    bars both called 1 would confuse whatever opens the file.
    """
    glued = documents[0]
    for document in documents[1:]:
        for index, part in enumerate(glued.iter("part")):
            others = list(document.iter("part"))
            if index >= len(others):
                break
            for measure in others[index].findall("measure"):
                part.append(measure)
    for part in glued.iter("part"):
        for number, measure in enumerate(part.findall("measure"), start=1):
            measure.set("number", str(number))
    return glued
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_omr.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add scorecap/omr.py tests/test_omr.py
git commit -m "feat: keep a transcribed heft together in one file"
```

---

### Task 3: Put the tenor back an octave

**Files:**
- Modify: `scorecap/omr.py`
- Test: `tests/test_omr.py`

**Interfaces:**
- Consumes: `read_score`, `glue` from Task 2.
- Produces: `fix_octave_clefs(score: ElementTree.Element) -> int`, returning how
  many voices it moved.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_omr.py`:

```python
def voice_xml(name: str, octave_change: str | None, octave: str = "5") -> str:
    change = f"<clef-octave-change>{octave_change}</clef-octave-change>" if octave_change else ""
    return (
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        f"<part-name>{name}</part-name></score-part></part-list>"
        '<part id="P1"><measure number="1"><attributes><clef>'
        f"<sign>G</sign><line>2</line>{change}</clef></attributes>"
        f"<note><pitch><step>F</step><octave>{octave}</octave></pitch>"
        "<duration>4</duration></note></measure></part></score-partwise>"
    )


def octaves(score) -> list[str]:
    return [element.text for element in score.iter("octave")]


def test_a_tenor_whose_octave_clef_went_unnoticed_sounds_an_octave_lower():
    score = ElementTree.fromstring(voice_xml("Tenor", None))

    assert omr.fix_octave_clefs(score) == 1
    assert octaves(score) == ["4"]
    assert score.find(".//clef/clef-octave-change").text == "-1"


def test_a_tenor_whose_clef_already_says_so_is_left_alone():
    score = ElementTree.fromstring(voice_xml("Tenor", "-1", octave="4"))

    assert omr.fix_octave_clefs(score) == 0
    assert octaves(score) == ["4"]


def test_a_voice_without_a_name_is_never_moved_on_a_hunch():
    score = ElementTree.fromstring(voice_xml("", None))

    assert omr.fix_octave_clefs(score) == 0
    assert octaves(score) == ["5"]


def test_a_soprano_stays_where_it_was_written():
    score = ElementTree.fromstring(voice_xml("Soprano", None))

    assert omr.fix_octave_clefs(score) == 0
    assert octaves(score) == ["5"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_omr.py -q`
Expected: FAIL, no attribute `fix_octave_clefs`.

- [ ] **Step 3: Write the code**

Add to `scorecap/omr.py`:

```python
TENOR_NAMES = frozenset({"t", "ten", "ten.", "tenor", "tenore", "tenöre", "tenor 1", "tenor 2"})


def _part_names(score: ElementTree.Element) -> dict[str, str]:
    names = {}
    for score_part in score.iter("score-part"):
        name = score_part.findtext("part-name") or ""
        names[score_part.get("id", "")] = name.strip().lower()
    return names


def fix_octave_clefs(score: ElementTree.Element) -> int:
    """Lower every tenor staff whose octave clef was overlooked.

    Audiveris reads the small 8 under a tenor clef from clean engraving but
    misses it on a scan, and then writes the voice an octave too high: every
    note right, the register wrong. Where the clef says plain G but the
    staff is named for tenors, the 8 was there. A staff without a name is
    left alone - a wrong guess is worse than a known quirk.
    """
    names = _part_names(score)
    moved = 0
    for part in score.iter("part"):
        clef = next(part.iter("clef"), None)
        if clef is None or clef.findtext("sign") != "G":
            continue
        if clef.find("clef-octave-change") is not None:
            continue
        if names.get(part.get("id", ""), "") not in TENOR_NAMES:
            continue
        for octave in part.iter("octave"):
            octave.text = str(int(octave.text) - 1)
        change = ElementTree.SubElement(clef, "clef-octave-change")
        change.text = "-1"
        moved += 1
    return moved
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_omr.py -q`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add scorecap/omr.py tests/test_omr.py
git commit -m "feat: keep a scanned tenor in the octave it was written"
```

---

### Task 4: Transcribe a PDF into a file

**Files:**
- Modify: `scorecap/omr.py`
- Test: `tests/test_omr.py`

**Interfaces:**
- Consumes: `find_audiveris`, `read_score`, `glue`, `fix_octave_clefs`.
- Produces: `class NothingFound(Exception)`,
  `run_audiveris(launcher: Path, source: Path, out_dir: Path, timeout: int = 1800) -> str`
  (its output, for the log) and
  `transcribe(source: Path, target: Path, work_dir: Path, run=run_audiveris, cancelled=lambda: False) -> Path`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_omr.py`:

```python
from pathlib import Path


def stub_audiveris(*files: str):
    """An Audiveris that writes the MusicXML it was told to, and nothing else."""

    def run(launcher, source, out_dir, timeout=1800):
        out_dir.mkdir(parents=True, exist_ok=True)
        for number, text in enumerate(files, start=1):
            (out_dir / f"score.mvt{number}.musicxml").write_text(text, encoding="utf-8")
        return "stub"

    return run


def test_a_transcribed_score_lands_under_the_name_the_user_chose(tmp_path, monkeypatch):
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    target = tmp_path / "Perseus.musicxml"

    written = omr.transcribe(
        tmp_path / "score.pdf",
        target,
        tmp_path / "work",
        run=stub_audiveris(score_xml(2), score_xml(3)),
    )

    assert written == target
    score = omr.read_score(target)
    assert len(score.find(".//part").findall("measure")) == 5


def test_a_score_with_nothing_on_it_leaves_no_file_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    target = tmp_path / "Perseus.musicxml"

    with pytest.raises(omr.NothingFound):
        omr.transcribe(tmp_path / "score.pdf", target, tmp_path / "work", run=stub_audiveris())

    assert not target.exists()


def test_a_failed_transcription_leaves_the_previous_file_intact(tmp_path, monkeypatch):
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    target = tmp_path / "Perseus.musicxml"
    target.write_text("older and still good", encoding="utf-8")

    with pytest.raises(omr.NothingFound):
        omr.transcribe(tmp_path / "score.pdf", target, tmp_path / "work", run=stub_audiveris())

    assert target.read_text(encoding="utf-8") == "older and still good"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_omr.py -q`
Expected: FAIL, no attribute `transcribe`.

- [ ] **Step 3: Write the code**

Add to `scorecap/omr.py`, with `import os`, `import subprocess` and
`from typing import Callable` at the top:

```python
class NothingFound(Exception):
    """Audiveris read the pages and found no music on them."""


def run_audiveris(
    launcher: Path, source: Path, out_dir: Path, timeout: int = 1800
) -> str:
    """Transcribe one file into `out_dir`; returns what Audiveris said."""
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            str(launcher),
            "-batch",
            "-transcribe",
            "-export",
            "-output",
            str(out_dir),
            "--",
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout + result.stderr


def transcribe(
    source: Path,
    target: Path,
    work_dir: Path,
    run: Callable[..., str] = run_audiveris,
    cancelled: Callable[[], bool] = lambda: False,
) -> Path:
    """Transcribe `source` and write the result to `target`.

    Written through a partial file that only replaces the old one at the
    end, so a run that breaks off leaves the previous export intact.
    """
    launcher = find_audiveris()
    output = run(launcher, source, work_dir)
    log.info("audiveris finished: %s", output.strip().splitlines()[-1:] or "no output")
    written = sorted(work_dir.rglob("*.mxl")) + sorted(work_dir.rglob("*.musicxml"))
    if not written or cancelled():
        raise NothingFound("no music was recognised")
    score = glue([read_score(path) for path in written])
    moved = fix_octave_clefs(score)
    if moved:
        log.info("lowered %d voice(s) whose octave clef was missed", moved)
    partial = target.with_name(target.name + ".part")
    ElementTree.ElementTree(score).write(partial, encoding="utf-8", xml_declaration=True)
    os.replace(partial, target)  # atomic on the same volume
    return target
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_omr.py -q`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add scorecap/omr.py tests/test_omr.py
git commit -m "feat: write a transcribed score without risking the last one"
```

---

### Task 5: Run it off the window

**Files:**
- Modify: `scorecap/tasks.py`
- Test: `tests/test_omr.py`

**Interfaces:**
- Consumes: `omr.transcribe`.
- Produces: `class MusicXmlSignals(QObject)` with `done = Signal(object)` (a
  `Path` on success, an `Exception` on failure) and `finished = Signal()`, and
  `class MusicXmlExport(BackgroundTask)` with `cancel()`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_omr.py`:

```python
def test_the_window_hears_about_a_finished_transcription(qapp, tmp_path, monkeypatch):
    from scorecap.tasks import MusicXmlExport, MusicXmlSignals

    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    target = tmp_path / "Perseus.musicxml"
    signals = MusicXmlSignals()
    seen = []
    signals.done.connect(seen.append)

    task = MusicXmlExport(
        tmp_path / "score.pdf", target, tmp_path / "work", signals, run=stub_audiveris(score_xml(1))
    )
    task.run()

    assert seen == [target]


def test_a_transcription_that_fails_reports_the_reason(qapp, tmp_path, monkeypatch):
    from scorecap.tasks import MusicXmlExport, MusicXmlSignals

    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    signals = MusicXmlSignals()
    seen = []
    signals.done.connect(seen.append)

    task = MusicXmlExport(
        tmp_path / "score.pdf",
        tmp_path / "Perseus.musicxml",
        tmp_path / "work",
        signals,
        run=stub_audiveris(),
    )
    task.run()

    assert isinstance(seen[0], omr.NothingFound)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_omr.py -q`
Expected: FAIL, `ImportError: cannot import name 'MusicXmlExport'`.

- [ ] **Step 3: Write the code**

Add to `scorecap/tasks.py`, with `from . import omr` among the imports:

```python
class MusicXmlSignals(QObject):
    done = Signal(object)   # the written Path, or the Exception that stopped it
    finished = Signal()


class MusicXmlExport(BackgroundTask):
    """Hands a rendered score to Audiveris without freezing the window."""

    def __init__(
        self,
        source: Path,
        target: Path,
        work_dir: Path,
        signals: MusicXmlSignals,
        run=omr.run_audiveris,
    ) -> None:
        super().__init__(signals)
        self._source = source
        self._target = target
        self._work_dir = work_dir
        self._run = run
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def _work(self) -> None:
        try:
            written = omr.transcribe(
                self._source,
                self._target,
                self._work_dir,
                run=self._run,
                cancelled=self._cancelled.is_set,
            )
        except (omr.AudiverisMissing, omr.NothingFound, OSError) as error:
            emit(self.signals.done, error)
            return
        emit(self.signals.done, written)

    def _failed(self) -> None:
        emit(self.signals.done, RuntimeError("the transcription crashed"))
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_omr.py -q`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add scorecap/tasks.py tests/test_omr.py
git commit -m "feat: transcribe without freezing the window"
```

---

### Task 6: The button and what it says

**Files:**
- Modify: `scorecap/app.py`
- Test: `tests/test_musicxml_ui.py` (new)

**Interfaces:**
- Consumes: `MusicXmlExport`, `MusicXmlSignals`, `omr.AudiverisMissing`,
  `omr.DOWNLOAD_URL`.
- Produces on `MainWindow`: `musicxml_source() -> Path` (the grey PDF handed
  over), `export_musicxml_to(path: Path, run=...) -> None` and
  `export_musicxml() -> None` (the button).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_musicxml_ui.py`:

```python
"""'Export as MusicXML' writes a file, and says plainly when it cannot."""

from pathlib import Path

import pytest
from PIL import Image

from scorecap import omr
from scorecap.model import Shot


def score_xml() -> str:
    return (
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        "<part-name>Soprano</part-name></score-part></part-list>"
        '<part id="P1"><measure number="1"><note><pitch><step>C</step>'
        "<octave>4</octave></pitch><duration>4</duration></note></measure>"
        "</part></score-partwise>"
    )


def stub_audiveris(launcher, source, out_dir, timeout=1800):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "score.musicxml").write_text(score_xml(), encoding="utf-8")
    return "stub"


@pytest.fixture()
def window(qapp, tmp_path):
    from scorecap.app import MainWindow

    win = MainWindow()
    path = tmp_path / "shot.png"
    Image.new("L", (1200, 300), "white").save(path)
    win.document.add(Shot(path=path, width=1200, height=300))
    win.rebuild()
    yield win
    win.close()


def test_a_transcribed_score_is_written_where_the_user_asked(window, tmp_path):
    target = tmp_path / "Perseus.musicxml"

    window.export_musicxml_to(target, run=stub_audiveris)
    window._musicxml_task.run()

    assert omr.read_score(target).find(".//part") is not None


def test_without_audiveris_the_window_explains_instead_of_failing(
    window, tmp_path, monkeypatch
):
    monkeypatch.setattr(omr, "find_audiveris", _missing)
    shown = []
    monkeypatch.setattr(
        "scorecap.app.QMessageBox.information", lambda *args: shown.append(args[2])
    )
    target = tmp_path / "Perseus.musicxml"

    window.export_musicxml_to(target, run=stub_audiveris)
    window._musicxml_task.run()

    assert shown and "Audiveris" in shown[0]
    assert not target.exists()


def _missing():
    raise omr.AudiverisMissing("not installed")
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_musicxml_ui.py -q`
Expected: FAIL, `AttributeError: 'MainWindow' object has no attribute
'export_musicxml_to'`.

- [ ] **Step 3: Add the button**

In `scorecap/app.py`, beside the shrink button (around line 224):

```python
        self.musicxml_button = self._button(self.tr("Export as MusicXML …"), icons.MUSICXML)
        self.musicxml_button.setToolTip(
            self.tr("Transcribe the score with Audiveris, for playing it back elsewhere")
        )
        self.musicxml_button.clicked.connect(self.export_musicxml)
```

and add it to the same bar as the shrink button:

```python
        bar.addWidget(self.musicxml_button)
```

In `scorecap/icons.py`, beside `SHRINK`:

```python
MUSICXML = "\ue8d6"      # quarter note
```

- [ ] **Step 4: Write the window's side**

In `scorecap/app.py`, next to `export`, with `from dataclasses import replace`,
`from . import omr` and `from .tasks import MusicXmlExport, MusicXmlSignals`
among the imports and `self._musicxml_task = None` beside the other task
attributes in `__init__`:

```python
    def musicxml_source(self) -> Path:
        """The score as Audiveris reads it best: grey, and without a footer.

        Grey beat black and white in every voice that was measured, and the
        footer sits where lyrics otherwise are. The print settings belong to
        the printer, not to the transcription.
        """
        settings = replace(self.settings, scan_mode="grey", footer_enabled=False)
        ready = usable_shots(self.document.shots)
        spans = (
            [staff_extent_of(s) for s in ready.shots] if settings.align_staff_ends else None
        )
        pages = paginate([s.effective_size for s in ready.shots], settings, spans)
        source = self._temp_dir / "for-audiveris.pdf"
        source.write_bytes(pdf.build(ready.shots, pages, settings))
        return source

    def export_musicxml_to(self, path: Path, run=omr.run_audiveris) -> None:
        """Start the transcription; the result arrives in _on_musicxml_done."""
        if self._musicxml_task is not None:
            return
        signals = MusicXmlSignals(self)
        signals.done.connect(self._on_musicxml_done)
        self._musicxml_task = self._track(
            MusicXmlExport(
                self.musicxml_source(), path, self._temp_dir / "audiveris", signals, run=run
            )
        )
        self.musicxml_button.setEnabled(False)
        self.status.setText(self.tr("Transcribing with Audiveris — this takes a while …"))
        QThreadPool.globalInstance().start(self._musicxml_task)

    def export_musicxml(self) -> None:
        stem = self._project_path.stem if self._project_path else self.tr("score")
        folder = self._last_folder("musicxml") or (
            str(self._project_path.parent) if self._project_path else ""
        )
        name, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save as MusicXML"),
            str(Path(folder) / f"{stem}.musicxml"),
            self.tr("MusicXML (*.musicxml)"),
        )
        if name:
            self._remember_folder("musicxml", Path(name))
            self.export_musicxml_to(Path(name))

    def _on_musicxml_done(self, outcome) -> None:
        self._musicxml_task = None
        self.musicxml_button.setEnabled(True)
        if isinstance(outcome, omr.AudiverisMissing):
            QMessageBox.information(
                self,
                self.tr("Audiveris is needed for this"),
                self.tr(
                    "ScoreCap has the pages; reading the notes off them is done by "
                    "Audiveris, a separate free program. Install it from {url} and "
                    "try again."
                ).format(url=omr.DOWNLOAD_URL),
            )
            return
        if isinstance(outcome, Exception):
            QMessageBox.critical(self, self.tr("Transcription failed"), str(outcome))
            return
        self.status.setText(self.tr("Transcribed: {name}").format(name=outcome.name))
```

**Known gap, deliberate:** the task can be cancelled (`MusicXmlExport.cancel`)
but nothing in the window calls it yet - the button only goes quiet while the
transcription runs. A *Cancel* next to the status line is a separate change,
worth having once the run time is known from real use.

Guard the button the way the export button is guarded, in `rebuild` beside
`self.export_button.setEnabled(bool(pages))`:

```python
        self.musicxml_button.setEnabled(bool(pages) and self._musicxml_task is None)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_musicxml_ui.py -q`
Expected: 2 passed.

- [ ] **Step 6: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: every test passes except the translation guard, which the next task
settles.

- [ ] **Step 7: Commit**

```bash
git add scorecap/app.py scorecap/icons.py tests/test_musicxml_ui.py
git commit -m "feat: export a score as MusicXML for playing it back"
```

---

### Task 7: Language and documentation

**Files:**
- Modify: `scorecap/translations/*.ts`, `README.md`, `docs/aufbau.md`
- Test: `tests/test_release_guards.py` (run, not changed)

**Interfaces:**
- Consumes: the strings added in Task 6.

- [ ] **Step 1: Update the translations**

```bash
.venv/Scripts/python.exe tools/update_translations.py
```

Then open `scorecap/translations/scorecap_de.ts` and give every new string its
German (`Als MusicXML exportieren …`, `Als MusicXML speichern`,
`Wird mit Audiveris übertragen — das dauert …`, `Übertragen: {name}`,
`Dafür wird Audiveris gebraucht`, `Übertragung fehlgeschlagen`, and the
explanation, which names Audiveris and the link). Run the tool once more so the
compiled `.qm` files match.

- [ ] **Step 2: Run the suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all tests pass, the translation guard included.

- [ ] **Step 3: Write the README section**

Add to `README.md`, after *Scans importieren*:

```markdown
## Als MusicXML exportieren

Wer eine Stimme zum Üben hören will, braucht sie als Datei: *Als MusicXML
exportieren …* liest die Noten aus dem Heft und schreibt sie als
`.musicxml`, das MuseScore und die üblichen Tablet-Apps öffnen und abspielen.

Die Erkennung übernimmt [Audiveris](https://github.com/Audiveris/audiveris/releases),
ein eigenes freies Programm; ScoreCap liefert es nicht mit. Fehlt es, sagt
ScoreCap beim Druck auf den Knopf, was zu tun ist.

Gemessen wurden 85 bis 100 % der Töne und Notenwerte je Stimme — genug zum
Üben, nicht genug zum blinden Vertrauen. Gerechnet wird eine Weile; das
Fenster bleibt bedienbar. Mehrere Stücke in einem Heft werden eine
durchlaufende Partitur.
```

- [ ] **Step 4: Write the module into the map**

Add to the table in `docs/aufbau.md`, beside `optimize.py`:

```markdown
| `omr.py` | Noten erkennen lassen und als MusicXML schreiben |
```

- [ ] **Step 5: Commit**

```bash
git add scorecap/translations README.md docs/aufbau.md
git commit -m "feat: offer the MusicXML export in German too"
```
