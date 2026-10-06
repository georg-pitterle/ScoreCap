"""Reading a score through Claude Code, against recorded replies only."""

import json

import pytest
from PIL import Image

from scorecap import omr, reader
from scorecap.reader import ClaudeCode, ClaudeLoggedOut, ClaudeMissing, ReadingFailed

SESSION = "7cd6f8a5-cd7f-48a3-ab3f-27f7041c48ff"


def opened(name: str) -> dict:
    """The line `claude -p --output-format stream-json` prints for a Read."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_01",
                    "name": "Read",
                    "input": {"file_path": rf"C:\Temp\claude\{name}"},
                }
            ],
        },
        "session_id": SESSION,
    }


LIMITS = {
    "type": "rate_limit_event",
    "rate_limit_info": {
        "status": "allowed",
        "rateLimitType": "five_hour",
        "unifiedWindows": {
            "five_hour": {"utilization": 0.1},
            "seven_day": {"utilization": 0.31},
        },
    },
}


def result(text: str, is_error: bool = False) -> dict:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": is_error,
        "num_turns": 3,
        "duration_ms": 5616,
        "session_id": SESSION,
        "total_cost_usd": 0.0315807,
        "usage": {
            "input_tokens": 17,
            "cache_creation_input_tokens": 11454,
            "cache_read_input_tokens": 60307,
            "output_tokens": 525,
        },
        "result": text,
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


def replying(*texts, events=None):
    """A Claude Code that answers with recorded lines, one reply per call.

    Each reply opens system-01.png first, as a real reading does.
    """
    asked = []
    replies = list(texts)

    def run(command, prompt, folder, cancelled):
        asked.append((command, prompt))
        lines = events or [
            opened("system-01.png"),
            LIMITS,
            result(replies.pop(0)),
        ]
        return [json.dumps(line) + "\n" for line in lines]

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
    text, _ = reader.read(systems, "", ClaudeCode(replying(GOOD)), tmp_path)

    assert text.startswith("voice S: Soprano, G")
    assert (tmp_path / "system-01.png").exists()


def test_claude_may_only_read_and_is_shown_the_hints(systems, tmp_path, installed):
    run = replying(GOOD)

    reader.read(systems, "staff 1: E4/G2*", ClaudeCode(run), tmp_path)

    command, prompt = run.asked[0]
    assert command[command.index("--allowedTools") + 1] == "Read"
    assert "staff 1: E4/G2*" in prompt


def test_the_users_own_plugins_and_hooks_stay_out_of_the_reading(
    systems, tmp_path, installed
):
    """They would ride along in every reading and cost the plan for nothing."""
    run = replying(GOOD)

    reader.read(systems, "", ClaudeCode(run), tmp_path)

    command, _ = run.asked[0]
    assert command[command.index("--setting-sources") + 1] == ""


def test_a_bar_that_does_not_add_up_is_sent_back_naming_it(
    systems, tmp_path, installed
):
    run = replying(TOO_LONG, GOOD)

    text, _ = reader.read(systems, "", ClaudeCode(run), tmp_path)

    assert "G5" not in text
    command, correction = run.asked[1]
    assert "bar 2, Soprano" in correction
    assert command[command.index("--resume") + 1] == SESSION


def test_after_three_corrections_the_reading_gives_up(systems, tmp_path, installed):
    run = replying(*[TOO_LONG] * 4)

    with pytest.raises(ReadingFailed, match="bar 2, Soprano"):
        reader.read(systems, "", ClaudeCode(run), tmp_path)

    assert len(run.asked) == 4


def test_the_window_hears_each_time_claude_opens_a_system(
    systems, tmp_path, installed
):
    seen = []

    reader.read(
        systems * 2,
        "",
        ClaudeCode(replying(GOOD)),
        tmp_path,
        progress=lambda reached: seen.append((reached.looked, reached.systems)),
    )

    assert seen[:2] == [(0, 2), (1, 2)]
    assert seen[-1] == (2, 2)


def test_what_every_reading_used_adds_up(systems, tmp_path, installed):
    _, usage = reader.read(
        systems, "", ClaudeCode(replying(TOO_LONG, GOOD)), tmp_path
    )

    assert usage.tokens_in == 2 * (17 + 11454 + 60307)
    assert usage.cost_usd == pytest.approx(2 * 0.0315807)
    assert (usage.five_hour, usage.seven_day) == (0.1, 0.31)


def test_without_claude_code_the_user_is_told_to_install_it(tmp_path, monkeypatch):
    monkeypatch.setattr(reader.shutil, "which", lambda name: None)
    monkeypatch.setattr(reader, "CANDIDATES", (tmp_path / "nowhere.exe",))

    with pytest.raises(ClaudeMissing):
        reader.find_claude()


def test_a_claude_code_that_is_not_signed_in_says_so(systems, tmp_path, installed):
    logged_out = replying(events=[result("Not logged in · Please run /login", True)])

    with pytest.raises(ClaudeLoggedOut):
        reader.read(systems, "", ClaudeCode(logged_out), tmp_path)


def test_a_claude_code_that_says_nothing_useful_is_reported_with_what_it_said(
    systems, tmp_path, installed
):
    def crashed(command, prompt, folder, cancelled):
        return ["Error: something broke inside\n"]

    with pytest.raises(ReadingFailed, match="something broke"):
        reader.read(systems, "", ClaudeCode(crashed), tmp_path)


def test_a_read_score_is_written_with_one_part_per_sung_line(
    systems, tmp_path, installed
):
    target = tmp_path / "Evening.musicxml"

    written, _ = reader.transcribe(
        systems, target, tmp_path / "work", backend=ClaudeCode(replying(GOOD))
    )

    parts = omr.read_score(written).iter("score-part")
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


def test_a_claude_code_that_never_answers_is_given_up_on(
    tmp_path, monkeypatch
):
    """A real process that outlives the limit is ended, not waited on."""
    import sys

    monkeypatch.setattr(reader, "TIMEOUT_S", 0.05)
    monkeypatch.setattr(reader, "WATCH_S", 0.05)
    sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]

    with pytest.raises(ReadingFailed, match="minutes"):
        list(reader.run_claude(sleeper, "", tmp_path, lambda: False))


def test_a_cancelled_reading_ends_the_process(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(reader, "WATCH_S", 0.05)
    sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]

    with pytest.raises(omr.Cancelled):
        list(reader.run_claude(sleeper, "", tmp_path, lambda: True))
