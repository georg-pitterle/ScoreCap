# OMR-Messstand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure which cut - whole page, system, or single staff - Audiveris
transcribes best, so the MusicXML feature can be designed on numbers instead of
hearsay.

**Architecture:** A throwaway harness outside the app. It renders the test PDFs
with ScoreCap's own cleanup, cuts them five ways, runs each piece through the
installed Audiveris in batch mode, reads pitch and duration out of the resulting
MusicXML and compares them against the MuseScore originals. Nothing lands in
`scorecap/`, nothing gets a test in `tests/`; the only committed artefact is the
results table.

**Tech Stack:** Python 3.14 from `.venv`, Pillow, PyMuPDF, `scorecap.scan` and
`scorecap.ink` as libraries, Audiveris 5.x via `bin\Audiveris.bat`, `zipfile` +
`xml.etree.ElementTree` + `difflib` from the standard library.

## Global Constraints

- The harness lives in `lab/`, which is git-ignored. The spec said scratchpad;
  a folder in the repo survives a new session and keeps `assets/` at a
  relative path. Nothing under `lab/` is ever committed.
- Test material: `assets/test_music_xml/` - `Dawn.pdf` / `Dawn.mxl` (clean
  MuseScore engraving), `Earth Song.pdf` / `Earth_Song.mxl` (scan). Git-ignored,
  never commit it.
- Run everything with `.venv/Scripts/python.exe`, from the repo root.
- Measured are pitch and duration only. Lyrics, dynamics, articulation, slurs
  are discarded on both sides of the comparison.
- No code in `scorecap/`, no file in `tests/`. This is a measurement, not a
  feature.
- Audiveris must be installed (console variant). Its launcher is
  `<install>/bin/Audiveris.bat`. If it is missing, stop and say so - do not
  fall back to another engine.
- Lines under 88 characters, `from __future__ import annotations` at the top of
  each module, English code and comments, as `AGENTS.md` demands.

---

## File Structure

| File | Responsibility |
|---|---|
| `lab/engine.py` | Run Audiveris on one image or PDF, return the `.mxl` path |
| `lab/pages.py` | A PDF to cleaned, deskewed grey page images |
| `lab/cuts.py` | One cleaned page to the strips of variants A-E |
| `lab/score.py` | A `.mxl` to `(pitch, duration)` per part, and the match |
| `lab/run.py` | The matrix: piece x variant, prints the table |
| `docs/superpowers/notes/2026-09-22-omr-ergebnisse.md` | The results, committed |

---

### Task 1: Drive Audiveris from Python

**Files:**
- Create: `lab/engine.py`
- Create: `lab/__init__.py` (empty)
- Modify: `.gitignore`

**Interfaces:**
- Produces: `find_audiveris() -> Path` and
  `transcribe(source: Path, out_dir: Path, timeout: int = 600) -> Path | None`,
  returning the written `.mxl` or `None` when Audiveris produced none.

- [ ] **Step 1: Ignore the harness**

Append to `.gitignore`:

```
# The OMR measuring harness is scratch work.
lab/
```

- [ ] **Step 2: Write the runner**

Create `lab/__init__.py` as an empty file, and `lab/engine.py`:

```python
"""Audiveris in batch mode: an image or PDF in, a MusicXML file out."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

CANDIDATES = (
    Path(r"C:\Program Files\Audiveris\bin\Audiveris.bat"),
    Path(r"C:\Program Files (x86)\Audiveris\bin\Audiveris.bat"),
    Path.home() / "AppData/Local/Programs/Audiveris/bin/Audiveris.bat",
)


def find_audiveris() -> Path:
    """The Audiveris launcher. AUDIVERIS_HOME wins over the usual places."""
    home = os.environ.get("AUDIVERIS_HOME")
    if home:
        launcher = Path(home) / "bin" / "Audiveris.bat"
        if launcher.exists():
            return launcher
    for candidate in CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Audiveris not found - install it or set AUDIVERIS_HOME"
    )


def transcribe(source: Path, out_dir: Path, timeout: int = 600) -> Path | None:
    """Transcribe one file, returning the .mxl Audiveris wrote.

    Returns None when it wrote none: a strip it refuses is a result of the
    experiment, not an error to raise.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            str(find_audiveris()),
            "-batch",
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
    written = sorted(out_dir.rglob("*.mxl"))
    if not written:
        log = out_dir / f"{source.stem}.audiveris.log"
        log.write_text(result.stdout + result.stderr, encoding="utf-8")
    return written[0] if written else None
```

- [ ] **Step 3: Run it on a whole page**

```bash
.venv/Scripts/python.exe -c "from pathlib import Path; from lab.engine import transcribe; print(transcribe(Path('assets/test_music_xml/Dawn.pdf'), Path('lab/out/smoke')))"
```

Expected: a path such as `lab/out/smoke/Dawn.mxl`, and the file exists. If it
prints `None`, read `lab/out/smoke/Dawn.audiveris.log` and fix the call before
going on - every later task depends on this one.

- [ ] **Step 4: Commit the ignore rule**

```bash
git add .gitignore
git commit -m "chore: keep the OMR measuring harness out of the repo"
```

---

### Task 2: Cleaned pages out of a PDF

**Files:**
- Create: `lab/pages.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `clean_pages(pdf: Path) -> list[Image.Image]` - grey page images,
  background flattened, edges cleared, skew undone, exactly as
  `scan.process_page` sees them before it cuts.

- [ ] **Step 1: Write the module**

Create `lab/pages.py`:

```python
"""A PDF to the cleaned grey pages ScoreCap would cut into systems."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from scorecap.scan import clear_edges, flatten_background, load_pages, skew_angle


def clean_pages(pdf: Path) -> list[Image.Image]:
    """Every page, flattened, de-bordered and straightened."""
    pages = []
    for image in load_pages(pdf):
        grey = clear_edges(flatten_background(image.convert("L")))
        angle = skew_angle(grey)
        if angle:
            grey = grey.rotate(angle, Image.BICUBIC, fillcolor=255)
        pages.append(grey)
    return pages
```

- [ ] **Step 2: Look at what comes out**

```bash
.venv/Scripts/python.exe -c "from pathlib import Path; from lab.pages import clean_pages; p = clean_pages(Path('assets/test_music_xml/Earth Song.pdf')); print(len(p), p[0].size); p[0].save('lab/out/page1.png')"
```

Expected: a page count, a size around 2500x3500, and `lab/out/page1.png` shows
white paper with black staves - no grey cast, no dark scanner border, staff
lines horizontal. If the page is crooked or grey, stop: every variant inherits
this.

---

### Task 3: The single-staff cut, and the question it answers

**Files:**
- Create: `lab/cuts.py`

**Interfaces:**
- Consumes: `clean_pages` from Task 2.
- Produces: `staff_strips(page: Image.Image, margin: float) -> list[Image.Image]`,
  where `margin` is the extra height above and below each staff as a multiple of
  the staff height (`0.0` for variant C, `1.0` for variant D).

- [ ] **Step 1: Write the cut**

Create `lab/cuts.py`:

```python
"""One cleaned page, cut the five ways the experiment compares."""

from __future__ import annotations

from PIL import Image, ImageFilter

from scorecap.ink import binary, staff_lines
from scorecap.scan import LINE_SPAN, _staves


def staff_strips(page: Image.Image, margin: float) -> list[Image.Image]:
    """Every five-line staff of the page, top to bottom.

    `margin` grows each strip above and below by that multiple of its own
    height: 0.0 keeps it tight, 1.0 takes in what hangs off the staff.
    """
    ink = binary(page).filter(ImageFilter.MaxFilter(3))
    strips = []
    for staff in _staves(staff_lines(ink, LINE_SPAN)):
        height = staff.bottom - staff.top
        grown = round(margin * height)
        strips.append(
            page.crop(
                (
                    0,
                    max(0, staff.top - grown),
                    page.width,
                    min(page.height, staff.bottom + grown),
                )
            )
        )
    return strips
```

- [ ] **Step 2: Cut a page and count**

```bash
.venv/Scripts/python.exe -c "from pathlib import Path; from lab.pages import clean_pages; from lab.cuts import staff_strips; page = clean_pages(Path('assets/test_music_xml/Dawn.pdf'))[0]; s = staff_strips(page, 0.0); print(len(s), [i.size for i in s[:3]]); s[0].save('lab/out/staff1.png')"
```

Expected: as many strips as there are staves on the first page (four voices per
system, so a multiple of four on a choral page), and `lab/out/staff1.png` holds
one staff with its notes.

- [ ] **Step 3: Answer the gating question**

```bash
.venv/Scripts/python.exe -c "from pathlib import Path; from lab.engine import transcribe; print(transcribe(Path('lab/out/staff1.png'), Path('lab/out/strip')))"
```

Expected: a path to an `.mxl`. **If this prints `None`, the experiment is over
for variants C and D** - note it in the results file in Task 6, and measure only
A, B and E. Do not try to talk Audiveris into it with extra options; refusing a
strip is the answer.

---

### Task 4: Pitch and duration out of MusicXML

**Files:**
- Create: `lab/score.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `parts(mxl: Path) -> list[list[tuple[str, float]]]` - one list per
  part, each note or rest as `(pitch, quarters)` with `pitch == "rest"` for a
  rest - and
  `match(found: list[tuple[str, float]], truth: list[tuple[str, float]]) -> float`,
  the share of the truth that was recognised, 0.0 to 1.0.

- [ ] **Step 1: Write the reader**

Create `lab/score.py`:

```python
"""MusicXML reduced to what you hear: pitch and length, part by part."""

from __future__ import annotations

import difflib
import zipfile
from pathlib import Path
from xml.etree import ElementTree

Note = tuple[str, float]


def _document(mxl: Path) -> ElementTree.Element:
    """The score inside an .mxl, or the file itself when it is plain XML."""
    if mxl.suffix.lower() != ".mxl":
        return ElementTree.parse(mxl).getroot()
    with zipfile.ZipFile(mxl) as archive:
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//rootfile")
        name = rootfile.get("full-path") if rootfile is not None else "score.xml"
        return ElementTree.fromstring(archive.read(name))


def _pitch(note: ElementTree.Element) -> str:
    pitch = note.find("pitch")
    if pitch is None:
        return "rest"
    step = pitch.findtext("step", "")
    octave = pitch.findtext("octave", "")
    alter = int(float(pitch.findtext("alter", "0") or 0))
    return f"{step}{alter:+d}{octave}"


def parts(mxl: Path) -> list[list[Note]]:
    """Every part as its sequence of (pitch, length in quarters).

    Lengths are divided by the measure's `divisions`, because Audiveris and
    MuseScore count in different units - only the ratio is comparable.
    """
    found = []
    for part in _document(mxl).iter("part"):
        notes: list[Note] = []
        divisions = 1.0
        for measure in part.iter("measure"):
            attribute = measure.find("attributes/divisions")
            if attribute is not None and attribute.text:
                divisions = float(attribute.text)
            for note in measure.iter("note"):
                if note.find("chord") is not None:
                    continue  # one voice: the chord's other notes are extra
                duration = float(note.findtext("duration", "0") or 0)
                notes.append((_pitch(note), round(duration / divisions, 3)))
        found.append(notes)
    return found


def match(found: list[Note], truth: list[Note]) -> float:
    """The share of `truth` that `found` gets right, 0.0 to 1.0.

    A sequence match, not a position-by-position one: a single note too many
    would otherwise mark everything after it as wrong.
    """
    if not truth:
        return 0.0
    return difflib.SequenceMatcher(None, found, truth, autojunk=False).ratio()
```

- [ ] **Step 2: Check the reader against itself**

```bash
.venv/Scripts/python.exe -c "from pathlib import Path; from lab.score import parts, match; p = parts(Path('assets/test_music_xml/Dawn.mxl')); print([len(x) for x in p]); print(match(p[0], p[0]))"
```

Expected: one note count per voice, each well above zero, and `1.0` for a part
against itself. A `0.0` or an empty list means the reader is wrong, not the
engine - fix it here.

- [ ] **Step 3: Check it against the other truth**

```bash
.venv/Scripts/python.exe -c "from pathlib import Path; from lab.score import parts, match; a = parts(Path('assets/test_music_xml/Dawn.mxl')); b = parts(Path('assets/test_music_xml/Earth_Song.mxl')); print([len(x) for x in b]); print(round(match(a[0], b[0]), 3))"
```

Expected: note counts for the second piece, and a low number for two different
pieces - well under 0.5. A high one means the comparison rewards nonsense.

---

### Task 5: The remaining four cuts

**Files:**
- Modify: `lab/cuts.py`

**Interfaces:**
- Consumes: `staff_strips` from Task 3.
- Produces: `cut(page: Image.Image, variant: str) -> list[Image.Image]` for
  variants `"A"`, `"B"`, `"C"`, `"D"`, `"E"`.

- [ ] **Step 1: Widen the imports**

Replace the import block at the top of `lab/cuts.py` with:

```python
from PIL import Image, ImageDraw, ImageFilter

from scorecap.ink import binary, staff_lines
from scorecap.scan import LINE_SPAN, _staves, find_systems
```

- [ ] **Step 2: Add the other variants**

Append to `lab/cuts.py`:

```python
def system_strips(page: Image.Image) -> list[Image.Image]:
    """Every system of the page, as ScoreCap cuts them for a capture."""
    return [page.crop(system.band) for system in find_systems(page)]


def without_lyrics(page: Image.Image) -> Image.Image:
    """The page with everything between two staves painted out.

    Lyrics are what stands there; the experiment measures pitch and length,
    so what the engine cannot misread cannot cost anything.
    """
    clean = page.copy()
    painter = ImageDraw.Draw(clean)
    ink = binary(page).filter(ImageFilter.MaxFilter(3))
    staves = _staves(staff_lines(ink, LINE_SPAN))
    for upper, lower in zip(staves, staves[1:]):
        top = upper.bottom + round(0.8 * (upper.bottom - upper.top))
        bottom = lower.top - round(0.8 * (lower.bottom - lower.top))
        if bottom > top:
            painter.rectangle((0, top, page.width, bottom), fill=255)
    return clean


def cut(page: Image.Image, variant: str) -> list[Image.Image]:
    """The page cut for one variant of the experiment."""
    if variant == "A":
        return [page]
    if variant == "B":
        return system_strips(page)
    if variant == "C":
        return staff_strips(page, 0.0)
    if variant == "D":
        return staff_strips(page, 1.0)
    if variant == "E":
        return [without_lyrics(page)]
    raise ValueError(f"unknown variant {variant!r}")
```

- [ ] **Step 3: Cut one page every way and look**

```bash
.venv/Scripts/python.exe -c "from pathlib import Path; from lab.pages import clean_pages; from lab.cuts import cut; page = clean_pages(Path('assets/test_music_xml/Earth Song.pdf'))[0]; [print(v, len(cut(page, v))) for v in 'ABCDE']; cut(page, 'E')[0].save('lab/out/nolyrics.png')"
```

Expected: `A 1`, `B` the number of systems, `C` and `D` the number of staves,
`E 1`. In `lab/out/nolyrics.png` the lyrics are gone and **no staff line is
touched** - if a staff lost its bottom line, raise the `0.8` factors until it
does not.

---

### Task 6: The table

**Files:**
- Create: `lab/run.py`
- Create: `docs/superpowers/notes/2026-09-22-omr-ergebnisse.md`

**Interfaces:**
- Consumes: `clean_pages`, `cut`, `transcribe`, `parts`, `match`.
- Produces: the printed table and the committed results file.

- [ ] **Step 1: Write the orchestrator**

Create `lab/run.py`:

```python
"""The experiment: every piece, every variant, one table of hit rates."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from .cuts import cut
from .engine import transcribe
from .pages import clean_pages
from .score import Note, match, parts

MATERIAL = Path("assets/test_music_xml")
PIECES = {
    "Dawn": (MATERIAL / "Dawn.pdf", MATERIAL / "Dawn.mxl"),
    "Earth Song": (MATERIAL / "Earth Song.pdf", MATERIAL / "Earth_Song.mxl"),
}
OUT = Path("lab/out")


def _found(pdf: Path, variant: str, work: Path) -> list[list[Note]]:
    """Every part Audiveris read out of this piece, cut this way.

    Strips are transcribed one by one, so a variant that yields one file per
    staff ends up with one part per file - which is exactly the comparison
    the reassembly question turns on.
    """
    collected: list[list[Note]] = []
    for page_number, page in enumerate(clean_pages(pdf), start=1):
        for index, piece in enumerate(cut(page, variant)):
            image = work / f"p{page_number}-{index:02d}.png"
            image.parent.mkdir(parents=True, exist_ok=True)
            piece.save(image)
            result = transcribe(image, work / f"out-{page_number}-{index:02d}")
            collected.extend(parts(result) if result else [[]])
    return collected


def _best(found: list[list[Note]], truth: list[Note]) -> float:
    """The best a single recognised part scores against this voice.

    Which strip holds which voice is only known once it is read, so every
    candidate is tried and the strongest counts.
    """
    return max((match(part, truth) for part in found), default=0.0)


def main(variants: str = "ABCDE") -> None:
    for name, (pdf, mxl) in PIECES.items():
        truth = parts(mxl)
        print(f"\n{name}: {len(truth)} voices, {sum(len(v) for v in truth)} notes")
        for variant in variants:
            work = OUT / name.replace(" ", "_") / variant
            started = time.monotonic()
            found = _found(pdf, variant, work)
            seconds = time.monotonic() - started
            scores = [f"{_best(found, voice):.0%}" for voice in truth]
            print(f"  {variant}: {' '.join(scores)}   {seconds:.0f}s")


if __name__ == "__main__":
    main(*sys.argv[1:])
```

- [ ] **Step 2: Run one variant first**

```bash
.venv/Scripts/python.exe -m lab.run A
```

Expected: two lines of percentages, one per piece, within a few minutes. Numbers
somewhere between 0% and 100% - all zeroes mean the parts never line up, and
that is a bug in `_best`, not a finding.

- [ ] **Step 3: Run the whole matrix**

```bash
.venv/Scripts/python.exe -m lab.run
```

Expected: five lines per piece. C and D take minutes: one JVM start per staff.
Let it finish and keep the output.

- [ ] **Step 4: Write down what came out**

Create `docs/superpowers/notes/2026-09-22-omr-ergebnisse.md` with the table as
it was printed, in German, and beneath it three short paragraphs:

- which variant won on the scan, which on the clean engraving;
- whether Audiveris accepted a single-staff strip at all;
- what that means for the feature - a page handed through, or cutting and
  reassembling, and what the next design has to solve.

Where a number surprises, name the suspicion in one sentence. Do not smooth
anything out: a variant that lost is a result.

- [ ] **Step 5: Commit the results**

```bash
git add docs/superpowers/notes/2026-09-22-omr-ergebnisse.md
git commit -m "docs: record which cut Audiveris reads best"
```

Nothing else is committed. `lab/` and `assets/test_music_xml/` stay out.
