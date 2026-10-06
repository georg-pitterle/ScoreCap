"""System images in, checked short notation and a MusicXML file out, read by Claude."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, Sequence
from xml.etree import ElementTree

from PIL import Image

from . import noteheads, transcript, voices
from .omr import Cancelled

log = logging.getLogger(__name__)

DOWNLOAD_URL = "https://claude.com/claude-code"
MODEL = "opus"
CORRECTIONS = 3         # rounds in which a reader may mend its own notation
TIMEOUT_S = 1800        # a long score takes Opus many minutes to read

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
class Reply:
    text: str
    session: str | None = None


class Backend(Protocol):
    def ask(self, prompt: str, folder: Path, session: str | None) -> Reply:
        """Answer `prompt`, with the images in `folder` at hand.

        `session` continues an earlier conversation, so a correction does
        not pay for reading every image again.
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


class ClaudeCode:
    """Claude Code run as `claude -p`, signed in with the user's own plan.

    A subscription without API access can still read scores this way. The
    reader gets the Read tool and nothing else: it has to open the images,
    and has no business writing or running anything.
    """

    def __init__(
        self,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        model: str = MODEL,
    ) -> None:
        self._run = run
        self._model = model

    def ask(self, prompt: str, folder: Path, session: str | None) -> Reply:
        command = [
            str(find_claude()),
            "-p",
            "--output-format",
            "json",
            "--allowedTools",
            "Read",
            "--model",
            self._model,
        ]
        if session:
            command += ["--resume", session]
        try:
            # Through stdin: hints for a long score outgrow a Windows command
            # line. No console window: ScoreCap has none to lend it.
            done = self._run(
                command,
                input=prompt,
                cwd=folder,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT_S,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise ReadingFailed(
                f"Claude Code did not answer within {TIMEOUT_S // 60} minutes"
            ) from None
        try:
            answer = json.loads(done.stdout)
        except json.JSONDecodeError:
            said = (done.stderr or done.stdout or "").strip()[-500:]
            if "/login" in said:
                raise ClaudeLoggedOut(said) from None
            raise ReadingFailed(said or "Claude Code gave no answer") from None
        text = str(answer.get("result") or "")
        if answer.get("is_error"):
            if "/login" in text or "log in" in text.lower():
                raise ClaudeLoggedOut(text)
            raise ReadingFailed(text or str(answer.get("subtype", "error")))
        return Reply(text, answer.get("session_id"))


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
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> str:
    """Notation for the systems that parses and whose every bar adds up.

    What the check finds is handed back for up to CORRECTIONS rounds; a
    reader that still has not got it right by then is not going to.
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
    for attempt in range(1, total + 1):
        if cancelled():
            raise Cancelled("the transcription was cancelled")
        if progress:
            progress(attempt, total)
        reply = backend.ask(prompt, folder, session)
        session = reply.session
        text = _notation(reply.text)
        try:
            transcript.parse(text)
        except transcript.TranscriptError as error:
            log.info("reading %d of %d did not add up:\n%s", attempt, total, error)
            if attempt == total:
                raise ReadingFailed(str(error)) from error
            prompt = CORRECTION.format(problems=str(error))
            continue
        return text
    raise AssertionError("unreachable")


def transcribe(
    system_images: Sequence[Image.Image],
    target: Path,
    work_dir: Path,
    backend: Backend | None = None,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> Path:
    """Read the systems and write one line per sung voice to `target`.

    Written through a partial file that only replaces the old one at the
    end, so a reading that breaks off leaves the previous export intact.
    """
    hints = noteheads.hints(system_images)
    text = read(
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
    return target

