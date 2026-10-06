"""System images in, checked short notation and a MusicXML file out, read by Claude."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
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
Treat each sung staff as one voice. Where a voice divides on one staff,
write chords (`G3+Bb3:h`); where it divides onto several staves, give each
staff its own voice. Leave out piano and other instruments. Give the voices
names as the score does (Soprano, Alto, Tenor, Bass, Solo ...).

A program has found the noteheads already. For each system and staff it
lists them bar by bar, each head as it reads under a treble and under a
bass clef (`B4/D3`; take the one the staff's clef says, an octave lower for
a tenor clef with an 8). `o` is an open head, `*` a filled one. It does not
see rhythm, accidentals, ties or rests - those are yours - and it can miss
or invent a head, so the image decides. Use it to get the pitches right:

{hints}

Check that every voice fills every bar before you answer. Reply with the
notation only, in one ``` block.
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
        for line in self._run(command, prompt, folder, cancelled):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                chatter.append(line)
                continue
            if not isinstance(event, dict):
                continue
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
        if result is None:
            said = "".join(chatter).strip()[-500:]
            if "/login" in said:
                raise ClaudeLoggedOut(said)
            raise ReadingFailed(said or "Claude Code gave no answer")
        text = str(result.get("result") or "")
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


def read(
    system_images: Sequence[Image.Image],
    hints: str,
    backend: Backend,
    folder: Path,
    progress: Callable[[Progress], None] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[str, Usage]:
    """Notation for the systems that parses and whose every bar adds up.

    What the check finds is handed back for up to CORRECTIONS rounds; a
    reader that still has not got it right by then is not going to. The
    usage counts every round, the failed ones too - they cost the same.
    """
    folder.mkdir(parents=True, exist_ok=True)
    names = []
    for number, image in enumerate(system_images, start=1):
        name = f"system-{number:02d}.png"
        image.save(folder / name)
        names.append(name)
    prompt = PROMPT.format(
        files=", ".join(names), notation=transcript.NOTATION, hints=hints
    )
    total = CORRECTIONS + 1
    session = None
    usage = Usage()
    seen: set[str] = set()

    def report(attempt: int) -> None:
        if progress:
            progress(Progress(attempt, total, len(seen), len(names), usage))

    for attempt in range(1, total + 1):
        if cancelled():
            raise Cancelled("the transcription was cancelled")
        report(attempt)

        def looked(name: str, attempt: int = attempt) -> None:
            if name in names and name not in seen:
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
        reply = backend.ask(
            prompt, folder, session, looked=looked, cancelled=cancelled
        )
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
        return text, usage
    raise AssertionError("unreachable")


def transcribe(
    system_images: Sequence[Image.Image],
    target: Path,
    work_dir: Path,
    backend: Backend | None = None,
    progress: Callable[[Progress], None] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
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
    return target, usage

