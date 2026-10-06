"""Reading a score through Claude Code, against recorded replies only."""

import json
import subprocess

import pytest
from PIL import Image

from scorecap import omr, reader
from scorecap.reader import ClaudeCode, ClaudeLoggedOut, ClaudeMissing, ReadingFailed

# The shape `claude -p --output-format json` prints, trimmed to what matters.
RECORDED = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "num_turns": 4,
    "session_id": "569456cf-768c-4098-843f-7e3ff3d13739",
    "result": "",
}
LOGGED_OUT = {
    "type": "result",
    "subtype": "success",
    "is_error": True,
    "session_id": "e0c1",
    "result": "Not logged in · Please run /login",
}

GOOD = """\
Here is the transcription:

```
voice S: Soprano, G
voice B: Bass, F
bar 3/4
S: C5:q D5:q E5:q
B: C3+G3:h.
bar
S: F5:h.
B: B2+F3:h.
```"""

TOO_LONG = GOOD.replace("F5:h.", "F5:h. G5:q")


def replying(*texts, raw=None):
    """A `subprocess.run` that answers with recorded replies, one per call."""
    asked = []
    replies = list(texts)

    def run(command, **kwargs):
        asked.append((command, kwargs["input"]))
        if raw is not None:
            stdout = json.dumps(raw)
        else:
            stdout = json.dumps({**RECORDED, "result": replies.pop(0)})
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    run.asked = asked
    return run


@pytest.fixture()
def installed(monkeypatch, tmp_path):
    monkeypatch.setattr(reader, "find_claude", lambda: tmp_path / "claude.exe")


@pytest.fixture(scope="module")
def systems():
    return [Image.new("L", (400, 120), 255)]


def test_a_score_claude_reads_comes_back_as_checked_notation(
    systems, tmp_path, installed
):
    text = reader.read(systems, "", ClaudeCode(replying(GOOD)), tmp_path)

    assert text.startswith("voice S: Soprano, G")
    assert (tmp_path / "system-01.png").exists()


def test_claude_may_only_read_and_is_shown_the_hints(systems, tmp_path, installed):
    run = replying(GOOD)

    reader.read(systems, "staff 1: E4/G2*", ClaudeCode(run), tmp_path)

    command, prompt = run.asked[0]
    assert command[command.index("--allowedTools") + 1] == "Read"
    assert "staff 1: E4/G2*" in prompt


def test_a_bar_that_does_not_add_up_is_sent_back_naming_it(
    systems, tmp_path, installed
):
    run = replying(TOO_LONG, GOOD)

    text = reader.read(systems, "", ClaudeCode(run), tmp_path)

    assert "G5" not in text
    command, correction = run.asked[1]
    assert "bar 2, Soprano" in correction
    assert command[command.index("--resume") + 1] == RECORDED["session_id"]


def test_after_three_corrections_the_reading_gives_up(systems, tmp_path, installed):
    run = replying(*[TOO_LONG] * 4)

    with pytest.raises(ReadingFailed, match="bar 2, Soprano"):
        reader.read(systems, "", ClaudeCode(run), tmp_path)

    assert len(run.asked) == 4


def test_without_claude_code_the_user_is_told_to_install_it(tmp_path, monkeypatch):
    monkeypatch.setattr(reader.shutil, "which", lambda name: None)
    monkeypatch.setattr(reader, "CANDIDATES", (tmp_path / "nowhere.exe",))

    with pytest.raises(ClaudeMissing):
        reader.find_claude()


def test_a_claude_code_that_is_not_signed_in_says_so(systems, tmp_path, installed):
    with pytest.raises(ClaudeLoggedOut):
        reader.read(systems, "", ClaudeCode(replying(raw=LOGGED_OUT)), tmp_path)


def test_a_read_score_is_written_with_one_part_per_sung_line(
    systems, tmp_path, installed
):
    target = tmp_path / "Evening.musicxml"

    reader.transcribe(
        systems, target, tmp_path / "work", backend=ClaudeCode(replying(GOOD))
    )

    parts = omr.read_score(target).iter("score-part")
    names = [part.findtext("part-name") for part in parts]
    assert names == ["Soprano", "Bass 1", "Bass 2"]


def test_a_reading_that_fails_leaves_the_previous_file_intact(
    systems, tmp_path, installed
):
    target = tmp_path / "Evening.musicxml"
    target.write_text("older and still good", encoding="utf-8")

    with pytest.raises(ReadingFailed):
        reader.transcribe(
            systems,
            target,
            tmp_path / "work",
            backend=ClaudeCode(replying(*[TOO_LONG] * 4)),
        )

    assert target.read_text(encoding="utf-8") == "older and still good"


def test_a_claude_code_that_never_answers_is_given_up_on(systems, tmp_path, installed):
    def hanging(command, **kwargs):
        raise subprocess.TimeoutExpired(command, reader.TIMEOUT_S)

    with pytest.raises(ReadingFailed, match="minutes"):
        reader.read(systems, "", ClaudeCode(hanging), tmp_path)
