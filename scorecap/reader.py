"""System images in, checked short notation and a MusicXML file out, read by Claude."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, Protocol, Sequence
from xml.etree import ElementTree

from PIL import Image

from . import noteheads, transcript, voices
from .omr import Cancelled

log = logging.getLogger(__name__)

DOWNLOAD_URL = "https://claude.com/claude-code"
MODEL = "opus"
CORRECTIONS = 3         # rounds in which a reader may mend its own notation
TIMEOUT_S = 1800        # a long score takes Opus many minutes to read
WATCH_S = 0.5           # how often a running reader is checked on
# Claude sees an image whole up to this long edge and scales a larger one
# down - a wide system loses its accidentals and dots to that.
SEEN_WHOLE = 1568
PIECE_WIDTH = 700       # a magnified piece covers this much of the system
PIECE_OVERLAP = 100     # so a note on a cut is whole in one of the pieces
MAGNIFY_MOST = 2.0      # beyond this a piece shows blur, not detail
PAUSE_FILE = "paused.json"

_LIMIT = re.compile(r"hit your .{0,40}limit|usage limit", re.IGNORECASE)

CANDIDATES = (
    Path.home() / ".local/bin/claude.exe",
    Path.home() / ".local/bin/claude",
)

PROMPT = """\
You are transcribing a choral score for rehearsal recordings. The score's
systems are the images {files} in the current directory, in reading order.
Open every one of them with the Read tool and read every bar of every voice.

Write the music down in this short notation and in nothing else:

{notation}
Write one voice per sung part, not per staff. A staff that carries two
parts - Soprano and Alto, or Tenor and Bass, as in a closed score - is two
voices: stems up belong to the upper part, stems down to the lower, and a
head with stems both ways is sung by both. Where one part divides on its
own (two heads on one stem), write a chord in that part's voice
(`G3+Bb3:h`); where a part divides onto several staves, give each staff its
own voice. A tenor voice takes clef G8, even where the score writes it in
the bass clef. Leave out piano and other instruments. Name the voices as
the score does (Soprano, Alto, Tenor, Bass, Solo ...).

A program has found the noteheads already. For each system and staff it
lists them bar by bar, each head as it reads under a treble and under a
bass clef (`B4/D3`; take the one the staff's clef says, an octave lower for
a tenor clef with an 8). `o` is an open head, `*` a filled one. It does not
see rhythm, accidentals, ties or rests - those are yours - and it can miss
or invent a head, so the image decides. Use it to get the pitches right:

{hints}

Each system is also there magnified, in pieces from left to right:

{pieces}

Open a piece where the system leaves you unsure - an accidental, a dot, a
tie, a rest, a ledger line - and only there.

Check that every voice fills every bar before you answer. Reply with the
notation only, in one ``` block.
"""

RESUME = """You were stopped before you finished. Carry on where you stopped: read what
you have not read yet, then reply with the complete notation for the whole
score - every bar, every voice - in one ``` block.
"""

CORRECTION = """\
The notation does not add up:

{problems}

Look at the bars named above in the images again and reply with the whole
corrected notation, in one ``` block.
"""


class ClaudeMissing(Exception):
    """Claude Code is not installed - the user can install it."""


class ClaudeLoggedOut(Exception):
    """Claude Code is installed but not signed in - the user can sign in."""


class ReadingFailed(Exception):
    """The reader gave up or answered with something that is no notation."""


class LimitReached(Exception):
    """The plan's usage limit stopped the reading; it can be taken up later.

    `resets` is when the plan is free again, if Claude Code said so.
    """

    def __init__(
        self, message: str, session: str | None, resets: datetime | None
    ) -> None:
        super().__init__(message)
        self.session = session
        self.resets = resets


@dataclass(frozen=True)
class Pause:
    """A reading the usage limit stopped: its session, and the round it was in."""

    session: str
    attempt: int

    def __post_init__(self) -> None:
        if not self.session:
            raise ValueError("a paused reading needs its session")
        if self.attempt < 1:
            raise ValueError("rounds count from 1")


@dataclass(frozen=True)
class Usage:
    """What a reading cost: tokens, their price at API rates, the plan's limits.

    On a subscription nothing is billed per token; what runs out is the
    share of the plan's five-hour and weekly limits, 0 to 1, when known.
    """

    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    five_hour: float | None = None
    seven_day: float | None = None

    def __post_init__(self) -> None:
        if self.tokens_in < 0 or self.tokens_out < 0 or self.cost_usd < 0:
            raise ValueError("usage cannot be negative")

    def __add__(self, later: Usage) -> Usage:
        """Both readings together; the limits as the later one saw them."""
        return Usage(
            self.tokens_in + later.tokens_in,
            self.tokens_out + later.tokens_out,
            self.cost_usd + later.cost_usd,
            later.five_hour if later.five_hour is not None else self.five_hour,
            later.seven_day if later.seven_day is not None else self.seven_day,
        )


@dataclass(frozen=True)
class Reply:
    text: str
    session: str | None = None
    usage: Usage = Usage()


@dataclass(frozen=True)
class Progress:
    """How far a reading has got, for the window to show."""

    attempt: int
    attempts: int
    looked: int     # systems the reader has opened so far
    systems: int
    usage: Usage = Usage()
    # Magnified pieces the reader needed: how much the systems alone hid.
    zoomed: tuple[str, ...] = ()


class Backend(Protocol):
    def ask(
        self,
        prompt: str,
        folder: Path,
        session: str | None,
        looked: Callable[[str], None] | None = None,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> Reply:
        """Answer `prompt`, with the images in `folder` at hand.

        `session` continues an earlier conversation, so a correction does
        not pay for reading every image again. `looked` hears the name of
        each file the reader opens.
        """


def find_claude() -> Path:
    """The Claude Code command, looked up afresh on every export."""
    found = shutil.which("claude")
    if found:
        return Path(found)
    for candidate in CANDIDATES:
        if candidate.exists():
            return candidate
    raise ClaudeMissing("Claude Code is not installed")


def run_claude(
    command: Sequence[str], prompt: str, folder: Path, cancelled: Callable[[], bool]
) -> Iterator[str]:
    """The lines Claude Code prints as it works, until it is done or stopped.

    The prompt goes in through stdin from a thread of its own: hints for a
    long score outgrow a Windows command line, and a full pipe must not
    hold up the reading. A watcher ends the process on cancel or timeout -
    waiting for the next line to check would wait as long as Claude thinks.
    """
    process = subprocess.Popen(
        command,
        cwd=folder,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        # No console window: ScoreCap has none to lend it.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    stopped: list[str] = []

    def feed() -> None:
        try:
            process.stdin.write(prompt)
            process.stdin.close()
        except OSError:
            pass  # it ended before reading; what it printed says why

    def watch() -> None:
        deadline = time.monotonic() + TIMEOUT_S
        while process.poll() is None:
            if cancelled():
                stopped.append("cancelled")
            elif time.monotonic() > deadline:
                stopped.append("timeout")
            if stopped:
                process.kill()
                return
            time.sleep(WATCH_S)

    threading.Thread(target=feed, daemon=True).start()
    threading.Thread(target=watch, daemon=True).start()
    with process:
        yield from process.stdout
    if "cancelled" in stopped:
        raise Cancelled("the transcription was cancelled")
    if "timeout" in stopped:
        raise ReadingFailed(
            f"Claude Code did not answer within {TIMEOUT_S // 60} minutes"
        )


def _usage(result: dict, limits: dict) -> Usage:
    tokens = result.get("usage") or {}
    windows = limits.get("unifiedWindows") or {}
    return Usage(
        tokens_in=int(tokens.get("input_tokens", 0))
        + int(tokens.get("cache_creation_input_tokens", 0))
        + int(tokens.get("cache_read_input_tokens", 0)),
        tokens_out=int(tokens.get("output_tokens", 0)),
        cost_usd=float(result.get("total_cost_usd") or 0.0),
        five_hour=(windows.get("five_hour") or {}).get("utilization"),
        seven_day=(windows.get("seven_day") or {}).get("utilization"),
    )


def _opened(event: dict) -> list[str]:
    """Names of the files one step of the reader's work opens."""
    content = (event.get("message") or {}).get("content") or []
    return [
        Path(str((item.get("input") or {}).get("file_path", ""))).name
        for item in content
        if isinstance(item, dict)
        and item.get("type") == "tool_use"
        and item.get("name") == "Read"
    ]


def _stop_at_limit(limits: dict, text: str, session: str | None) -> None:
    """Raise LimitReached if the plan's limit, not the score, ended the reading.

    Claude Code says so in its answer ("You've hit your session limit") or
    in the limits it reports; a notation never reads like either.
    """
    rejected = limits.get("status") == "rejected"
    if not rejected and not (_LIMIT.search(text) and "```" not in text):
        return
    resets_at = limits.get("resetsAt")
    resets = datetime.fromtimestamp(resets_at).astimezone() if resets_at else None
    raise LimitReached(text.strip() or "usage limit reached", session, resets)


def _share(fraction: float | None) -> str:
    return "?" if fraction is None else f"{fraction:.0%}"


class ClaudeCode:
    """Claude Code run as `claude -p`, signed in with the user's own plan.

    A subscription without API access can still read scores this way. The
    reader gets the Read tool and nothing else: it has to open the images,
    and has no business writing or running anything. The user's own
    settings, plugins and hooks stay out too - they would ride along in
    every reading and cost the plan for nothing.
    """

    def __init__(self, run=run_claude, model: str = MODEL) -> None:
        self._run = run
        self._model = model

    def ask(
        self,
        prompt: str,
        folder: Path,
        session: str | None,
        looked: Callable[[str], None] | None = None,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> Reply:
        command = [
            str(find_claude()),
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            # --tools takes every other tool away; --allowedTools alone
            # only spares Read the question and leaves Bash to the user's
            # settings, where it may well be allowed.
            "--tools",
            "Read",
            "--allowedTools",
            "Read",
            "--model",
            self._model,
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--disable-slash-commands",
        ]
        if session:
            command += ["--resume", session]
        result: dict | None = None
        limits: dict = {}
        chatter: list[str] = []
        current = session
        for line in self._run(command, prompt, folder, cancelled):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                chatter.append(line)
                continue
            if not isinstance(event, dict):
                continue
            current = event.get("session_id") or current
            kind = event.get("type")
            if kind == "assistant":
                for name in _opened(event):
                    log.debug("Claude opened %s", name)
                    if looked:
                        looked(name)
            elif kind == "rate_limit_event":
                limits = event.get("rate_limit_info") or {}
            elif kind == "result":
                result = event
        said = "".join(chatter).strip()[-500:]
        text = str((result or {}).get("result") or "")
        _stop_at_limit(limits, text if result else said, current)
        if result is None:
            if "/login" in said:
                raise ClaudeLoggedOut(said)
            raise ReadingFailed(said or "Claude Code gave no answer")
        if result.get("is_error"):
            if "/login" in text or "log in" in text.lower():
                raise ClaudeLoggedOut(text)
            raise ReadingFailed(text or str(result.get("subtype", "error")))
        usage = _usage(result, limits)
        log.info(
            "Claude answered after %.0f s in %s turns: %d tokens in, %d out, "
            "%.2f USD at API prices; plan used %s of five hours, %s of the week",
            (result.get("duration_ms") or 0) / 1000,
            result.get("num_turns", "?"),
            usage.tokens_in,
            usage.tokens_out,
            usage.cost_usd,
            _share(usage.five_hour),
            _share(usage.seven_day),
        )
        return Reply(text, result.get("session_id"), usage)


def _notation(text: str) -> str:
    """The notation out of a reply, with or without a ``` block around it."""
    if "```" not in text:
        return text.strip()
    inside = text.split("```", 2)[1]
    return inside.split("\n", 1)[1] if "\n" in inside else inside


def magnified(image: Image.Image) -> list[Image.Image]:
    """The system in overlapping pieces, each enlarged as far as is worth it.

    Enlarged until Claude would scale it down again, but at most twice:
    a narrow capture gains from it, past that only the blur grows. A system
    that fits whole and cannot be enlarged has no pieces.
    """
    width, height = image.size
    piece = min(width, PIECE_WIDTH)
    scale = max(1.0, min(MAGNIFY_MOST, SEEN_WHOLE / max(piece, height)))
    count = max(1, math.ceil((width - PIECE_OVERLAP) / (piece - PIECE_OVERLAP)))
    if count == 1 and scale == 1.0:
        return []
    step = (width - piece) / (count - 1) if count > 1 else 0
    size = (round(piece * scale), round(height * scale))
    return [
        image.crop((round(n * step), 0, round(n * step) + piece, height)).resize(
            size, Image.LANCZOS
        )
        for n in range(count)
    ]


def work_folder(root: Path, system_images: Sequence[Image.Image]) -> Path:
    """The folder a reading of exactly these systems works in.

    Named after the images rather than made afresh: a reading the usage
    limit stopped can only be taken up from the folder it began in, and
    only if the captures are still the same.
    """
    digest = hashlib.sha256()
    for image in system_images:
        digest.update(f"{image.mode}{image.size}".encode())
        digest.update(image.tobytes())
    return root / digest.hexdigest()[:16]


def paused(folder: Path) -> Pause | None:
    """The reading the usage limit stopped in this folder, if there is one."""
    try:
        saved = json.loads((folder / PAUSE_FILE).read_text(encoding="utf-8"))
        return Pause(str(saved["session"]), int(saved["attempt"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_images(
    system_images: Sequence[Image.Image], folder: Path
) -> dict[str, list[str]]:
    """Each system's file name, with the names of its magnified pieces."""
    pieces: dict[str, list[str]] = {}
    for number, image in enumerate(system_images, start=1):
        name = f"system-{number:02d}"
        image.save(folder / f"{name}.png")
        pieces[f"{name}.png"] = []
        for part, enlarged in enumerate(magnified(image), start=1):
            enlarged.save(folder / f"{name}-zoom-{part}.png")
            pieces[f"{name}.png"].append(f"{name}-zoom-{part}.png")
    return pieces


def read(
    system_images: Sequence[Image.Image],
    hints: str,
    backend: Backend,
    folder: Path,
    progress: Callable[[Progress], None] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    resume: bool = False,
) -> tuple[str, Usage]:
    """Notation for the systems that parses and whose every bar adds up.

    What the check finds is handed back for up to CORRECTIONS rounds; a
    reader that still has not got it right by then is not going to. The
    usage counts every round, the failed ones too - they cost the same.

    A reading the usage limit stops is noted in `folder`; with `resume` the
    next one carries on in that session instead of starting over.
    """
    folder.mkdir(parents=True, exist_ok=True)
    pause = paused(folder) if resume else None
    (folder / PAUSE_FILE).unlink(missing_ok=True)
    pieces = _write_images(system_images, folder)
    names = list(pieces)
    if pause is None:
        listing = "\n".join(
            f"{name}: {', '.join(parts)}" for name, parts in pieces.items() if parts
        )
        prompt = PROMPT.format(
            files=", ".join(names),
            notation=transcript.NOTATION,
            hints=hints,
            pieces=listing or "(none - every system is shown whole)",
        )
    else:
        prompt = RESUME
        log.info("taking up the reading of session %s", pause.session)
    zoomable = {piece for parts in pieces.values() for piece in parts}
    total = CORRECTIONS + 1
    session = pause.session if pause else None
    usage = Usage()
    seen: set[str] = set()
    zoomed: set[str] = set()

    def report(attempt: int) -> None:
        if progress:
            progress(
                Progress(
                    attempt,
                    total,
                    len(seen),
                    len(names),
                    usage,
                    tuple(sorted(zoomed)),
                )
            )

    for attempt in range(pause.attempt if pause else 1, total + 1):
        if cancelled():
            raise Cancelled("the transcription was cancelled")
        report(attempt)

        def looked(name: str, attempt: int = attempt) -> None:
            if name in zoomable and name not in zoomed:
                zoomed.add(name)
                log.info("Claude magnified %s", name)
                report(attempt)
            elif name in names and name not in seen:
                seen.add(name)
                report(attempt)

        log.info(
            "asking Claude (%s), reading %d of %d, %d system(s) in %s",
            "continuing" if session else "new session",
            attempt,
            total,
            len(names),
            folder,
        )
        try:
            reply = backend.ask(
                prompt, folder, session, looked=looked, cancelled=cancelled
            )
        except LimitReached as stop:
            stopped_in = stop.session or session
            if stopped_in:
                (folder / PAUSE_FILE).write_text(
                    json.dumps({"session": stopped_in, "attempt": attempt}),
                    encoding="utf-8",
                )
            raise
        session = reply.session
        usage = usage + reply.usage
        seen.update(names)  # whatever it skipped, this reading is over
        report(attempt)
        text = _notation(reply.text)
        try:
            transcript.parse(text)
        except transcript.TranscriptError as error:
            log.info("reading %d of %d did not add up:\n%s", attempt, total, error)
            if attempt == total:
                raise ReadingFailed(str(error)) from error
            prompt = CORRECTION.format(problems=str(error))
            continue
        log.info(
            "Claude magnified %d of %d piece(s) in %d of %d system(s)",
            len(zoomed),
            len(zoomable),
            len({name.split("-zoom-")[0] for name in zoomed}),
            len(names),
        )
        return text, usage
    raise AssertionError("unreachable")


def transcribe(
    system_images: Sequence[Image.Image],
    target: Path,
    work_dir: Path,
    backend: Backend | None = None,
    progress: Callable[[Progress], None] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    resume: bool = False,
) -> tuple[Path, Usage]:
    """The file written, one line per sung voice, and what reading it used.

    Written through a partial file that only replaces the old one at the
    end, so a reading that breaks off leaves the previous export intact.
    """
    hints = noteheads.hints(system_images)
    text, usage = read(
        system_images,
        hints,
        backend or ClaudeCode(),
        work_dir,
        progress=progress,
        cancelled=cancelled,
        resume=resume,
    )
    if cancelled():
        raise Cancelled("the transcription was cancelled")
    log.info("notation as read:\n%s", text)
    try:
        score = voices.split(transcript.parse(text))
    except ValueError as error:  # a voice divided past belief: a misreading
        raise ReadingFailed(str(error)) from error
    partial = target.with_name(target.name + ".part")
    ElementTree.ElementTree(transcript.to_musicxml(score)).write(
        partial, encoding="utf-8", xml_declaration=True
    )
    os.replace(partial, target)  # atomic on the same volume
    shutil.rmtree(work_dir, ignore_errors=True)  # nothing left to take up
    return target, usage

