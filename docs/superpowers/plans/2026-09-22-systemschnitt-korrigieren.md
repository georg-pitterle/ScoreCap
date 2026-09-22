# Correcting a System Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user pull a system that the scan import cut apart back
together, by cropping on the whole page instead of on the band the import saved.

**Architecture:** The import keeps the cleaned, deskewed page as a PNG of its
own in the session folder and hands back, per system, which page it came from
and where it sat on it. The window holds that mapping for the session only. The
edit dialog gains one button that swaps its canvas from the band to the page;
the crop then runs over the page, and the corrected capture points at the page
file. `Shot`, `project.py` and the `.scorecap` format stay untouched.

**Tech Stack:** Python 3.14 from `.venv`, PySide6, Pillow, pytest + pytest-qt.

## Global Constraints

- Code, docstrings, comments and test names in English. `docs/` in German.
- Every user-visible text goes through `self.tr(...)`; after adding one, run
  `.venv/Scripts/python.exe tools/update_translations.py` and hand-translate
  the new entries in `scorecap/translations/scorecap_de.ts`, or
  `tests/test_release_guards.py` fails.
- Every file starts with `from __future__ import annotations`; imports inside
  the package are relative.
- Data classes are frozen; changes go through `dataclasses.replace`.
- Lines stay under 88 characters.
- Each module keeps its own `log = logging.getLogger(__name__)`.
- Run tests with `.venv/Scripts/python.exe -m pytest`.
- Conventional Commits, English, imperative, naming the benefit.

---

### Task 1: The page a system was cut from

The import throws the page away today. Keep it, and record where each system
sat on it.

**Files:**
- Modify: `scorecap/model.py` (add `PageSource` after `Shot`)
- Modify: `scorecap/scan.py:66-83` (`PageResult`, `ImportResult`),
  `scorecap/scan.py` (`process_page`, `import_scans`)
- Test: `tests/test_scan.py`

**Interfaces:**
- Consumes: `scorecap.model.Shot`, `scorecap.scan.process_page`
- Produces:
  - `model.PageSource(page: Shot, region: tuple[int, int, int, int])`
  - `PageResult.sources: dict[Path, PageSource]` - keyed by the band shot's
    `path`; empty when no staves were found
  - `ImportResult.sources: dict[Path, PageSource]` - the same, merged over all
    pages and files

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_scan.py`, in the `--- whole pages ---` section after
`test_process_page_makes_one_straight_shot_per_system`:

```python
def test_every_system_can_be_found_again_on_the_page_it_came_from(tmp_path):
    image, _ = page([1, 2, 1], lyrics=True)
    scan = shadowed(image).rotate(1.2, Image.BICUBIC, fillcolor=200)
    result = process_page(scan, tmp_path)
    for number, shot in enumerate(result.shots):
        source = result.sources[shot.path]
        with Image.open(source.page.path) as whole:
            assert whole.size == (source.page.width, source.page.height)
            system = whole.crop(source.region)
        staves = 2 if number == 1 else 1
        assert horizontal_line_sharpness(system) >= 5 * staves


def test_the_page_reaches_past_the_system_to_its_neighbour(tmp_path):
    """The point of keeping it: a cut that fell wrong can be taken back."""
    image, _ = page([1, 1])
    result = process_page(image, tmp_path)
    first, second = (result.sources[shot.path] for shot in result.shots)
    assert first.page.path == second.page.path
    with Image.open(first.page.path) as whole:
        both = whole.crop((0, first.region[1], whole.width, second.region[3]))
    assert horizontal_line_sharpness(both) >= 10


def test_a_page_without_staves_has_nothing_to_go_back_to(tmp_path):
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    ImageDraw.Draw(image).rectangle([100, 100, 800, 200], fill=0)
    result = process_page(image, tmp_path)
    assert result.sources == {}
```

And in the import section, after
`test_import_scans_collects_shots_and_reports_odd_pages`:

```python
def test_import_scans_remembers_the_page_behind_every_system(tmp_path):
    image, _ = page([1, 1])
    path = tmp_path / "scan.png"
    image.save(path)
    result = import_scans([path], tmp_path / "out")
    assert {shot.path for shot in result.shots} == set(result.sources)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scan.py -k "found_again or neighbour or nothing_to_go_back or remembers_the_page" -v`
Expected: FAIL with `AttributeError: 'PageResult' object has no attribute 'sources'`

- [ ] **Step 3: Add `PageSource` to the model**

In `scorecap/model.py`, after the `Shot` class and before `normalize_move`:

```python
@dataclass(frozen=True)
class PageSource:
    """The scanned page a capture was cut from, and where it sat on it.

    A cut between two systems can fall in the wrong place, and the band the
    import saved then holds half a system. The page is what the editing
    dialog needs to take such a cut back; it lives only as long as the
    session, so nothing of this is written to a project.
    """

    page: Shot
    region: tuple[int, int, int, int]
```

- [ ] **Step 4: Carry the sources out of `process_page`**

In `scorecap/scan.py`, extend the imports and result types:

```python
from dataclasses import dataclass, field
```

```python
from .model import PageSource, Shot
```

```python
@dataclass(frozen=True)
class PageResult:
    shots: list[Shot]
    found_staves: bool
    # Where each shot came from, so a cut between systems can be taken back.
    sources: dict[Path, PageSource] = field(default_factory=dict)
```

```python
@dataclass(frozen=True)
class ImportResult:
    """What an import produced; page lists name "file, page n"."""

    shots: list[Shot]
    pages: int
    whole: list[str]    # no staves found - kept as one capture
    blank: list[str]    # nothing on it - skipped
    errors: list[str]
    sources: dict[Path, PageSource] = field(default_factory=dict)
```

In `process_page`, replace the loop over `systems` and its `return` with:

```python
    whole_page = _save(_whitened(grey), (0, 0, grey.width, grey.height), target_dir)
    shots = []
    sources = {}
    for system in systems:
        band_left, band_top = system.band[:2]
        band = grey.crop(system.band)
        content = (
            system.content[0] - band_left,
            system.content[1] - band_top,
            system.content[2] - band_left,
            system.content[3] - band_top,
        )
        padding = max(2, (content[3] - content[1]) // 60)
        tilt = skew_angle(band.crop(content), limit=0.5)
        if abs(tilt) >= STRAIGHT_ENOUGH:
            band = band.rotate(tilt, Image.BICUBIC, fillcolor=255)
            # Turning about the middle moves the ends up or down a little.
            shift = math.ceil(band.width / 2 * math.tan(math.radians(abs(tilt)))) + 1
            content = (
                content[0],
                max(0, content[1] - shift),
                content[2],
                min(band.height, content[3] + shift),
            )
        finished = _whitened(band)
        shot = _save(finished, _trimmed(finished, content, padding), target_dir)
        shots.append(shot)
        sources[shot.path] = PageSource(page=whole_page, region=system.content)
    return PageResult(shots=shots, found_staves=True, sources=sources)
```

The page needs no cleaning of its own: `_whitened` works pixel by pixel, so a
band's pixels on the page are the band's pixels.

In `import_scans`, declare the dict, fill it and hand it on - all four
`ImportResult(...)` constructions in the function get it:

```python
    sources: dict[Path, PageSource] = {}
```

```python
                if cancelled():
                    return ImportResult(shots, pages, whole, blank, errors, sources)
```

```python
                result = process_page(image, target_dir)
                pages += 1
                shots.extend(result.shots)
                sources.update(result.sources)
```

```python
    return ImportResult(shots, pages, whole, blank, errors, sources)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scan.py tests/test_scan_ui.py tests/test_i18n.py -q`
Expected: PASS, no failures

- [ ] **Step 6: Commit**

```bash
git add scorecap/model.py scorecap/scan.py tests/test_scan.py
git commit -m "feat: keep the page a scanned system was cut from"
```

---

### Task 2: A way from the band to the page in the edit dialog

**Files:**
- Modify: `scorecap/cropdialog.py` (`_CropCanvas`, `CropDialog`)
- Modify: `scorecap/translations/scorecap_de.ts` (generated, then translated)
- Test: `tests/test_cropdialog.py`

**Interfaces:**
- Consumes: `model.PageSource` from Task 1
- Produces:
  - `CropDialog(shot, parent=None, palette=LIGHT, source: PageSource | None = None)`
  - `CropDialog.page_button: QPushButton` - disabled when there is no source
  - `CropDialog.show_page() -> None` - swaps the canvas to the page
  - `CropDialog.shot -> Shot` - the capture the crop belongs to; the page
    after a swap, the band before it
  - `_CropCanvas.show_image(pixmap: QPixmap, crop: tuple[int, int, int, int]) -> None`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cropdialog.py`, at the end of the file, together with its
helper:

```python
# --- going back to the whole page -------------------------------------------


def system_and_page(tmp_path):
    """A band the import saved, and the page it was cut from."""
    from scorecap.model import PageSource

    whole = Image.new("L", (200, 400), 255)
    page_path = tmp_path / "page.png"
    whole.save(page_path)
    band_path = tmp_path / "band.png"
    whole.crop((0, 0, 200, 100)).save(band_path)
    band = Shot(
        path=band_path,
        width=200,
        height=100,
        crop=(10, 10, 190, 90),
        scan=True,
        erasures=((20, 20, 40, 40),),
    )
    source = PageSource(
        page=Shot(path=page_path, width=200, height=400, scan=True),
        region=(10, 10, 190, 90),
    )
    return band, source


def test_a_capture_without_a_page_stays_on_its_own_image(tmp_path, qapp):
    from scorecap.cropdialog import CropDialog

    band, _ = system_and_page(tmp_path)
    dialog = CropDialog(band)
    assert not dialog.page_button.isEnabled()
    dialog.show_page()
    assert dialog.shot.path == band.path
    assert dialog.crop == (10, 10, 190, 90)


def test_the_page_opens_on_the_system_that_was_cut_from_it(tmp_path, qapp):
    from scorecap.cropdialog import CropDialog

    band, source = system_and_page(tmp_path)
    dialog = CropDialog(band, source=source)
    assert dialog.page_button.isEnabled()
    dialog.show_page()
    assert dialog.shot.path == source.page.path
    assert dialog.crop == source.region
    assert not dialog.page_button.isEnabled()  # one way; cancelling goes back


def test_the_erasures_of_the_band_do_not_follow_onto_the_page(tmp_path, qapp):
    """They sit in the band's pixels, and the band was straightened alone."""
    from scorecap.cropdialog import CropDialog

    band, source = system_and_page(tmp_path)
    dialog = CropDialog(band, source=source)
    dialog.show_page()
    assert dialog.erasures == ()


def test_on_the_page_the_crop_can_take_in_what_lies_below(tmp_path, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from scorecap.cropdialog import CropDialog

    band, source = system_and_page(tmp_path)
    dialog = CropDialog(band, source=source)
    dialog.show_page()
    dialog.set_mode("crop")
    canvas = dialog._canvas
    canvas.resize(200, 400)  # one widget pixel per image pixel
    QTest.mousePress(canvas, Qt.LeftButton, pos=QPoint(100, 90))  # bottom edge
    QTest.mouseMove(canvas, QPoint(100, 300))
    QTest.mouseRelease(canvas, Qt.LeftButton, pos=QPoint(100, 300))
    assert dialog.crop == (10, 10, 190, 300)


def test_a_vanished_page_takes_the_way_back_with_it(tmp_path, qapp):
    from scorecap.cropdialog import CropDialog

    band, source = system_and_page(tmp_path)
    source.page.path.unlink()
    dialog = CropDialog(band, source=source)
    dialog.show_page()
    assert dialog.shot.path == band.path
    assert not dialog.page_button.isEnabled()
```

Extend the German test at `tests/test_cropdialog.py:47`
(`test_the_dialog_speaks_german`) by one label:

```python
    assert {"Abbrechen", "Übernehmen", "Zuschneiden", "Radierer", "Ganze Seite"} <= labels
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cropdialog.py -k "page" -v`
Expected: FAIL with `AttributeError: 'CropDialog' object has no attribute 'page_button'`

- [ ] **Step 3: Let the canvas take a different image**

In `scorecap/cropdialog.py`, add the logger under the imports:

```python
import logging
```

```python
log = logging.getLogger(__name__)
```

Add to `_CropCanvas`, after `reset`:

```python
    def show_image(
        self, pixmap: QPixmap, crop: tuple[int, int, int, int]
    ) -> None:
        """A different image under the same dialog, with a crop to start on.

        The erasures do not come along: they are rectangles in the pixels of
        the image that is being left behind.
        """
        self._pixmap = pixmap
        self._crop = crop
        self._erasures = []
        self._start = self._now = None
        self._drag = None
        self.erasures_changed.emit()
        self.update()
```

- [ ] **Step 4: Give the dialog the button and the swap**

In `CropDialog.__init__`, take the source and keep the shot:

```python
    def __init__(
        self,
        shot: Shot,
        parent: QWidget | None = None,
        palette: Palette = LIGHT,
        source: PageSource | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit"))
        self._shot = shot
        self._source = source
        self._canvas = _CropCanvas(
            QPixmap(str(shot.path)), shot.crop, shot.erasures, palette
        )
```

with the import at the top of the file:

```python
from .model import PageSource, Shot
```

Build the button next to the existing `reset_button`:

```python
        self.page_button = QPushButton(self.tr("Whole page"))
        self.page_button.setObjectName("Quiet")
        self.page_button.setEnabled(source is not None)
        self.page_button.setToolTip(
            self.tr("Show the whole scanned page, to take in a system cut apart")
            if source is not None
            else self.tr("The scanned page is kept only while the session lasts")
        )
        self.page_button.clicked.connect(self.show_page)
```

and put it into the bottom row, left of the stretch:

```python
        row = QHBoxLayout()
        row.addWidget(reset_button)
        row.addWidget(self.page_button)
        row.addStretch(1)
        row.addWidget(buttons)
```

Add the property and the swap, after `reset`:

```python
    @property
    def shot(self) -> Shot:
        """The capture the crop and the erasures belong to."""
        return self._shot

    def show_page(self) -> None:
        """Swap the band for the page it was cut from. Cancelling goes back."""
        if self._source is None:
            return
        pixmap = QPixmap(str(self._source.page.path))
        if pixmap.isNull():  # the session folder was cleared under us
            log.info("the scanned page is gone: %s", self._source.page.path)
            self._source = None
            self.page_button.setEnabled(False)
            return
        self._canvas.show_image(pixmap, self._source.region)
        self._shot = self._source.page
        self._source = None
        self.page_button.setEnabled(False)
        self._update_actions()
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cropdialog.py -v`
Expected: PASS except `test_the_dialog_speaks_german`, which still fails on the
missing German translation

- [ ] **Step 6: Refresh and translate the texts**

Run: `.venv/Scripts/python.exe tools/update_translations.py`

Then open `scorecap/translations/scorecap_de.ts` and fill the three new
`CropDialog` entries, removing their `type="unfinished"`:

| source | translation |
|---|---|
| `Whole page` | `Ganze Seite` |
| `Show the whole scanned page, to take in a system cut apart` | `Die ganze gescannte Seite zeigen, um ein zerschnittenes System wieder einzufangen` |
| `The scanned page is kept only while the session lasts` | `Die gescannte Seite bleibt nur, solange die Sitzung läuft` |

Run `.venv/Scripts/python.exe tools/update_translations.py` again so the `.qm`
files are compiled from the finished `.ts`.

- [ ] **Step 7: Run the tests again**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cropdialog.py tests/test_release_guards.py -q`
Expected: PASS, no failures

- [ ] **Step 8: Commit**

```bash
git add scorecap/cropdialog.py scorecap/translations tests/test_cropdialog.py
git commit -m "feat: offer the whole page when editing a scanned system"
```

---

### Task 3: Wire the page through the window

**Files:**
- Modify: `scorecap/app.py:130-150` (state), `:644-655` (`_on_scans_imported`),
  `:798-815` (`edit_selected`), `:965-976` (`load_from`)
- Test: `tests/test_scan_ui.py`

**Interfaces:**
- Consumes: `ImportResult.sources` from Task 1, `CropDialog(..., source=...)`,
  `CropDialog.shot` from Task 2
- Produces: nothing later tasks rely on

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_scan_ui.py`, at the end, with the import at the top of the
file changed to:

```python
from tests.test_scan import horizontal_line_sharpness, page
```

```python
def correct_on_the_page(window, qtbot, tmp_path, monkeypatch):
    """Import two systems, then crop the first one over both on the page."""
    from scorecap.cropdialog import CropDialog

    window.import_files([scan(tmp_path, [1, 1])])
    qtbot.waitUntil(lambda: not window.is_importing, timeout=30_000)

    def take_the_whole_page(dialog):
        dialog.show_page()
        whole = dialog.shot
        dialog._canvas._crop = (0, 0, whole.width, whole.height)
        return True

    monkeypatch.setattr(CropDialog, "exec", take_the_whole_page)
    window.shot_list.setCurrentRow(0)
    window.edit_selected()


def test_a_system_cut_apart_can_be_taken_in_again(
    window, tmp_path, qtbot, monkeypatch
):
    correct_on_the_page(window, qtbot, tmp_path, monkeypatch)
    corrected = window.document.shots[0]
    with Image.open(corrected.path) as whole:
        kept = whole.crop(corrected.crop or (0, 0, corrected.width, corrected.height))
    assert horizontal_line_sharpness(kept) >= 10
    assert len(window.document.shots) == 2  # the neighbour is the user's to delete


def test_undo_puts_the_cut_system_back(window, tmp_path, qtbot, monkeypatch):
    window.import_files([scan(tmp_path, [1, 1])])
    qtbot.waitUntil(lambda: not window.is_importing, timeout=30_000)
    was = window.document.shots[0]
    correct_on_the_page(window, qtbot, tmp_path, monkeypatch)
    window.undo()
    assert window.document.shots[0] == was


def test_a_reopened_project_has_no_page_to_go_back_to(
    window, tmp_path, qtbot, monkeypatch
):
    from scorecap.cropdialog import CropDialog

    window.import_files([scan(tmp_path, [1, 1])])
    qtbot.waitUntil(lambda: not window.is_importing, timeout=30_000)
    target = tmp_path / "noten.scorecap"
    window.save_to(target)
    window.load_from(target)
    offered = []
    monkeypatch.setattr(
        CropDialog, "exec", lambda dialog: offered.append(dialog.page_button.isEnabled())
    )
    window.shot_list.setCurrentRow(0)
    window.edit_selected()
    assert offered == [False]
```

`from PIL import Image` is already imported at the top of the file.

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scan_ui.py -k "taken_in_again or puts_the_cut_system_back or no_page_to_go_back" -v`
Expected: FAIL. The window does not pass a source yet, so `show_page` does
nothing and the capture stays on its band: `test_a_system_cut_apart_can_be_taken_in_again`
fails at `assert horizontal_line_sharpness(kept) >= 10` with about 5.

- [ ] **Step 3: Hold the sources for the session**

In `scorecap/app.py`, next to `self._temp_dir` in `__init__`:

```python
        # Which page each imported system was cut from. Not saved: a project
        # keeps captures, not the scans behind them.
        self._scan_sources: dict[Path, PageSource] = {}
```

with the import extended:

```python
from .model import Document, PageSource, Shot, normalize_move
```

Fill it in `_on_scans_imported`, right after `self.scan_button.setEnabled(True)`:

```python
        self._scan_sources.update(result.sources)
```

And empty it in `load_from`, right after `self.document.replace_all(shots)`:

```python
        self._scan_sources.clear()
```

- [ ] **Step 4: Let the dialog swap the capture**

Replace the body of `edit_selected` from the dialog on:

```python
        dialog = CropDialog(
            shot, self, self.palette_tokens, self._scan_sources.get(shot.path)
        )
        if not dialog.exec():
            return
        base = dialog.shot
        crop = dialog.crop
        if dialog.erasures != base.erasures:
            # Fresh white at an edge is white margin; let the crop close in.
            crop = crop_after_erasing(
                replace(base, crop=crop, erasures=dialog.erasures), self.settings
            )
        if base.path == shot.path:
            self.document.set_edits(index, crop, dialog.erasures)
        else:
            self.document.replace_shot(
                index, replace(base, crop=crop, erasures=dialog.erasures)
            )
        self.rebuild()
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scan_ui.py -v`
Expected: PASS, no failures

- [ ] **Step 6: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, no failures

- [ ] **Step 7: Commit**

```bash
git add scorecap/app.py tests/test_scan_ui.py
git commit -m "feat: recrop a scanned system on the page it came from"
```

---

### Task 4: Say so in the docs, and check it on the real scan

**Files:**
- Modify: `docs/verarbeitung.md`
- Modify: `docs/manual-test.md`

**Interfaces:**
- Consumes: everything from Tasks 1-3
- Produces: nothing

- [ ] **Step 1: Describe the way back in `docs/verarbeitung.md`**

German, as everything under `docs/` is. A new section between
`## Bündige Notenlinien` and `## Dateigröße`:

```markdown
## Ein falscher Systemschnitt

Geschnitten wird zwischen zwei Notenzeilen, die keine Taktlinie verbindet.
Ist diese Taktlinie im Scan unterbrochen, fällt ein vierstimmiges System in
zwei Hälften, und die Aufnahme hält nur Sopran und Alt.

Der Import hebt deshalb die gereinigte, geradegestellte Seite als eigenes Bild
auf und merkt sich zu jeder Aufnahme, wo auf dieser Seite ihr System stand. Im
Bearbeiten-Dialog führt **Ganze Seite** dorthin zurück: der Zuschnitt läuft
dann über die Seite und kann das abgetrennte Nachbarsystem wieder einsammeln;
die überzählige Aufnahme löscht der Nutzer.

Die Radierungen der Aufnahme bleiben dabei zurück — sie sitzen in den Pixeln
des Bandes, das für sich noch einmal geradegestellt wurde, und träfen auf der
Seite daneben. Rückgängig holt beides zurück.

Die Seite lebt nur, solange die Sitzung läuft: im Projekt stehen Aufnahmen,
nicht die Scans dahinter. Nach dem Öffnen eines gespeicherten Projekts ist der
Knopf grau.
```

- [ ] **Step 2: Add the manual check to `docs/manual-test.md`**

As point 9 at the end of the numbered list under `## Scans`, after
„Schließen während des Imports":

```markdown
9. **Falscher Systemschnitt.** `assets/test_music_xml/Earth Song.pdf`
   importieren; auf Seite 1 zerfällt das erste System in Sopran/Alt und
   Tenor/Bass. Erste Aufnahme *Bearbeiten*, *Ganze Seite*, auf *Zuschneiden*
   schalten, Unterkante über Tenor und Bass ziehen, übernehmen, die zweite
   Aufnahme löschen.
   Erwartet: die Vorschau zeigt das System vollständig und in einem Stück.
   Danach dieselbe Aufnahme erneut bearbeiten: *Ganze Seite* ist grau.
```

- [ ] **Step 3: Run the release guards**

Run: `.venv/Scripts/python.exe -m pytest tests/test_release_guards.py -q`
Expected: PASS, no failures

- [ ] **Step 4: Commit**

```bash
git add docs/verarbeitung.md docs/manual-test.md
git commit -m "docs: describe taking back a wrong system cut"
```
