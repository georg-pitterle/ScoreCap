"""Score images to MusicXML: Audiveris in, one playable file out."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Callable, Sequence
from xml.etree import ElementTree
from xml.parsers import expat

log = logging.getLogger(__name__)

DOWNLOAD_URL = "https://github.com/Audiveris/audiveris/releases"

CANDIDATES = (
    Path(r"C:\Program Files\Audiveris\Audiveris.exe"),
    Path(r"C:\Program Files (x86)\Audiveris\Audiveris.exe"),
    Path.home() / "AppData/Local/Programs/Audiveris/Audiveris.exe",
)
LAUNCHERS = ("Audiveris.exe", "bin/Audiveris.bat")

# What only draws the page. `notations` takes the drawn slurs, ties and
# articulations with it; the sounding `tie` sits outside it and stays.
SILENT = frozenset(
    {
        "stem",
        "beam",
        "accidental",
        "notations",
        "lyric",
        "harmony",
        "print",
        "system-layout",
        "staff-layout",
        "staff-details",
        "defaults",
        "credit",
        "bar-style",
    }
)

# Audiveris announces the page count once and then tags every line of its
# chatter with the sheet it belongs to: "INFO [score#2] ... | GRID".
SHEET_TOTAL = re.compile(r"\b(\d+) sheets? in ")
SHEET_AT_WORK = re.compile(r"^\S+\s+\[[^\[\]#]*#(\d+)\]")

# What a <sound> is worth keeping a direction for: the tempo, and the jumps
# that decide which bar comes next. Not its dynamics.
AUDIBLE_SOUND = ("tempo", "dacapo", "segno", "coda", "tocoda", "fine")

TENOR_NAMES = frozenset(
    {"t", "ten", "ten.", "tenor", "tenore", "tenöre", "tenor 1", "tenor 2"}
)


class AudiverisMissing(Exception):
    """Audiveris is not installed - the one error the user can act on."""


class NothingFound(Exception):
    """Audiveris read the pages and found no music on them."""


class Cancelled(Exception):
    """The user stopped the transcription; nothing was written."""


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


def _parse(data: bytes) -> ElementTree.Element:
    """Parse MusicXML, refusing a document that declares its own entities.

    A real MusicXML file names the Recordare DTD and nothing else, so the
    DOCTYPE itself stays welcome. An entity declared inside it is not: a
    handful of nested ones expand into gigabytes and take the process with
    them. External entities expat refuses on its own.
    """
    builder = ElementTree.TreeBuilder()
    parser = expat.ParserCreate()

    def refuse(*_args: object) -> None:
        raise ValueError("the file declares XML entities")

    parser.EntityDeclHandler = refuse
    parser.StartElementHandler = builder.start
    parser.EndElementHandler = builder.end
    parser.CharacterDataHandler = builder.data
    try:
        parser.Parse(data, True)
    except expat.ExpatError as error:
        raise ElementTree.ParseError(str(error)) from error
    return builder.close()


def read_score(path: Path) -> ElementTree.Element:
    """The score in a MusicXML file, packed (.mxl) or plain."""
    if path.suffix.lower() != ".mxl":
        return _parse(path.read_bytes())
    with zipfile.ZipFile(path) as archive:
        container = _parse(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//rootfile")
        name = rootfile.get("full-path") if rootfile is not None else "score.xml"
        return _parse(archive.read(name))


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


def _in_reading_order(paths: Sequence[Path]) -> list[Path]:
    """Sorted so that mvt2 comes before mvt10, as plain sorting would not."""
    return sorted(
        paths,
        key=lambda path: [
            int(part) if part.isdigit() else part
            for part in re.split(r"(\d+)", path.name)
        ],
    )


def sheet_total(line: str) -> int | None:
    """How many pages Audiveris found, if this line says so."""
    match = SHEET_TOTAL.search(line)
    return int(match.group(1)) if match else None


def sheet_at_work(line: str) -> int | None:
    """Which page this line of chatter belongs to, if any.

    Only the tag the log puts in front of every line, never a sheet list
    inside the message: "sheets:[#1#2#3#4#5]" would otherwise read as
    page 5 and let the count start at the end.
    """
    match = SHEET_AT_WORK.search(line)
    return int(match.group(1)) if match else None


def run_audiveris(
    launcher: Path,
    source: Path,
    out_dir: Path,
    progress: Callable[[int, int], None] | None = None,
    timeout: int = 1800,
) -> str:
    """Transcribe one file into `out_dir`; returns what Audiveris said.

    Read line by line rather than in one go: a page takes ten seconds or
    more, and the window has nothing to say meanwhile unless it listens.
    Both streams go into one pipe - two pipes read in turn deadlock as soon
    as one of them fills.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
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
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    said: list[str] = []
    total = 0
    reached = 0
    with process:
        for line in process.stdout:
            said.append(line)
            total = sheet_total(line) or total
            sheet = sheet_at_work(line)
            # Dozens of lines per page; the window only wants the change.
            # Forwards only: a line out of turn must not walk the count back.
            if progress and sheet is not None and sheet > reached:
                reached = sheet
                progress(sheet, total)
        process.wait(timeout=timeout)
    return "".join(said)


def transcribe(
    source: Path,
    target: Path,
    work_dir: Path,
    run: Callable[..., str] = run_audiveris,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Transcribe `source` and write the result to `target`.

    Written through a partial file that only replaces the old one at the
    end, so a run that breaks off leaves the previous export intact.
    """
    launcher = find_audiveris()
    output = run(launcher, source, work_dir, progress=progress)
    log.info("audiveris finished: %s", output.strip().splitlines()[-1:] or "no output")
    written = _in_reading_order(
        list(work_dir.rglob("*.mxl")) + list(work_dir.rglob("*.musicxml"))
    )
    if cancelled():
        raise Cancelled("the transcription was cancelled")
    if not written:
        raise NothingFound("no music was recognised")
    score = glue([read_score(path) for path in written])
    moved = fix_octave_clefs(score)
    if moved:
        log.info("lowered %d voice(s) whose octave clef was missed", moved)
    playable_only(score)
    partial = target.with_name(target.name + ".part")
    ElementTree.ElementTree(score).write(
        partial, encoding="utf-8", xml_declaration=True
    )
    os.replace(partial, target)  # atomic on the same volume
    return target


def _is_silent(element: ElementTree.Element) -> bool:
    """Does this element leave the playback exactly as it was?"""
    if element.tag in SILENT:
        return True
    if element.tag == "direction":
        # Kept for a tempo or a jump, not for a "dolce" and not for a
        # forte: a dynamic marking carries <sound dynamics="..."> too, and
        # would slip through a test that asks only whether a sound is there.
        if element.find(".//metronome") is not None:
            return False
        return not any(
            sound.get(name)
            for sound in element.iter("sound")
            for name in AUDIBLE_SOUND
        )
    if element.tag == "barline":
        # A repeat changes what is played; a thick line at the end does not.
        return element.find("repeat") is None and element.find("ending") is None
    return False


def playable_only(score: ElementTree.Element) -> ElementTree.Element:
    """The same score with everything that does not sound taken out.

    The file is there to be played, and half of what Audiveris writes is
    engraving: stems, beams, page breaks, lyrics, chord symbols. None of it
    reaches the ear, and it is what the recognition gets wrong most often -
    a lyric line that slipped stands under the wrong notes forever.

    What sounds stays, including the parts that look like decoration: `tie`
    binds a note to the next, `time-modification` shortens a triplet,
    `chord` makes two notes one. `attributes` is left whole - without its
    clef the file no longer opens as a score, and 60 elements are no prize.
    """
    for parent in list(score.iter()):
        for child in list(parent):
            if _is_silent(child):
                parent.remove(child)
            elif child.tag == "rest":
                for placement in list(child):  # display-step, display-octave
                    child.remove(placement)
    return score
