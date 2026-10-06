"""'Export as MusicXML' writes a file, and says plainly when it cannot."""

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


def stub_audiveris(launcher, source, out_dir, progress=None, timeout=1800):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "score.musicxml").write_text(score_xml(), encoding="utf-8")
    return "stub"


def _missing():
    raise omr.AudiverisMissing("not installed")


@pytest.fixture()
def window(qapp, tmp_path):
    from scorecap.app import MainWindow

    win = MainWindow()
    path = tmp_path / "shot.png"
    Image.new("L", (1200, 300), "white").save(path)
    win.document.add(Shot(path=path, width=1200, height=300))
    win.rebuild()
    shown = []
    plain = win.status.setText
    win.status.setText = lambda text: (shown.append(text), plain(text))[1]
    win.shown_status = shown
    yield win
    win.close()


def test_a_transcribed_score_is_written_where_the_user_asked(window, tmp_path, qtbot):
    target = tmp_path / "Perseus.musicxml"

    window.export_musicxml_to(target, run=stub_audiveris)
    qtbot.waitUntil(lambda: not window.is_transcribing, timeout=30_000)

    assert omr.read_score(target).find(".//part") is not None


def test_without_audiveris_the_window_explains_instead_of_failing(
    window, tmp_path, qtbot, monkeypatch
):
    monkeypatch.setattr(omr, "find_audiveris", _missing)
    shown = []
    monkeypatch.setattr(
        "scorecap.app.QMessageBox.information", lambda *args: shown.append(args[2])
    )
    target = tmp_path / "Perseus.musicxml"

    window.export_musicxml_to(target, run=stub_audiveris)
    qtbot.waitUntil(lambda: not window.is_transcribing, timeout=30_000)

    assert shown and "Audiveris" in shown[0]
    assert not target.exists()


def counting_audiveris(launcher, source, out_dir, progress=None, timeout=1800):
    """An Audiveris that reports three pages before it writes anything."""
    if progress:
        progress(1, 0)      # the page count is not known yet
        progress(2, 3)
        progress(3, 3)
    return stub_audiveris(launcher, source, out_dir, timeout=timeout)


def test_the_status_line_counts_the_pages_as_audiveris_reaches_them(
    window, tmp_path, qtbot
):
    window.export_musicxml_to(tmp_path / "Perseus.musicxml", run=counting_audiveris)
    qtbot.waitUntil(lambda: not window.is_transcribing, timeout=30_000)

    assert any("3 of 3" in text for text in window.shown_status)


def test_before_the_page_count_is_known_only_the_page_is_named(window, tmp_path):
    window._on_musicxml_progress(1, 0)

    assert "page 1" in window.status.text()
    assert " of " not in window.status.text()


# --- read by Claude -------------------------------------------------------------


class RecordedClaude:
    """A reader that answers with notation it was given, never a live call."""

    def __init__(self, text: str, usage=None) -> None:
        self.text = text
        self.usage = usage

    def ask(self, prompt, folder, session, looked=None, cancelled=lambda: False):
        from scorecap.reader import Reply, Usage

        if looked:
            looked("system-01.png")
        return Reply(self.text, "s1", self.usage or Usage())


TWO_BASSES = """```
voice B: Bass, F
bar 4/4
B: C3+G3:w
```"""


def test_claude_writes_one_line_per_voice_where_the_user_asked(
    window, tmp_path, qtbot
):
    target = tmp_path / "Evening.musicxml"

    window.export_musicxml_with_claude_to(target, backend=RecordedClaude(TWO_BASSES))
    qtbot.waitUntil(lambda: not window.is_transcribing, timeout=30_000)

    parts = omr.read_score(target).iter("score-part")
    names = [part.findtext("part-name") for part in parts]
    assert names == ["Bass 1", "Bass 2"]
    assert any("Evening" in text for text in window.shown_status)


def test_without_claude_code_the_window_explains_instead_of_failing(
    window, tmp_path, qtbot, monkeypatch
):
    from scorecap import reader

    def missing():
        raise reader.ClaudeMissing("not installed")

    monkeypatch.setattr(reader, "find_claude", missing)
    shown = []
    monkeypatch.setattr(
        "scorecap.app.QMessageBox.information", lambda *args: shown.append(args[2])
    )
    target = tmp_path / "Evening.musicxml"

    window.export_musicxml_with_claude_to(target)
    qtbot.waitUntil(lambda: not window.is_transcribing, timeout=30_000)

    assert shown and "Claude Code" in shown[0]
    assert not target.exists()


def reached(attempt=1, looked=0, systems=4):
    from scorecap.reader import Progress

    return Progress(attempt, 4, looked, systems)


def test_the_status_line_says_when_claude_mends_its_own_reading(window):
    window._on_claude_progress(reached(attempt=2, looked=4))

    assert "1 of 3" in window.status.text()


def test_the_bar_fills_as_claude_opens_one_system_after_the_other(window):
    window._on_claude_progress(reached(looked=1))

    assert "system 2 of 4" in window.status.text()
    assert not window.progress_bar.isHidden()
    assert (window.progress_bar.value(), window.progress_bar.maximum()) == (1, 4)


def test_once_every_system_is_read_the_bar_only_runs(window):
    window._on_claude_progress(reached(looked=4))

    assert window.progress_bar.maximum() == 0


def test_after_reading_the_status_line_says_what_it_used_of_the_plan(
    window, tmp_path, qtbot
):
    from scorecap.reader import Usage

    used = Usage(tokens_in=182_400, tokens_out=3_000, cost_usd=1.84,
                 five_hour=0.12, seven_day=0.31)
    target = tmp_path / "Evening.musicxml"

    window.export_musicxml_with_claude_to(
        target, backend=RecordedClaude(TWO_BASSES, used)
    )
    qtbot.waitUntil(lambda: not window.is_transcribing, timeout=30_000)

    assert "182 k tokens" in window.status.text()
    assert "12 % of five hours, 31 % of the week" in window.status.text()
    assert window.progress_bar.isHidden()


def test_without_the_plan_s_limits_the_price_at_api_rates_is_named(window):
    from scorecap.reader import Usage

    text = window.usage_text(Usage(tokens_in=40_000, cost_usd=0.5))

    assert "0.50 US$" in text



class LimitedClaude:
    """A reader the usage limit stops once; afterwards it answers."""

    def __init__(self) -> None:
        self.sessions = []

    def ask(self, prompt, folder, session, looked=None, cancelled=lambda: False):
        from datetime import datetime

        from scorecap.reader import LimitReached, Reply

        self.sessions.append(session)
        if len(self.sessions) == 1:
            raise LimitReached("limit", "s-stopped", datetime(2026, 10, 6, 22, 10))
        return Reply(TWO_BASSES, session)


def test_the_usage_limit_is_explained_with_the_time_it_ends(
    window, tmp_path, qtbot, monkeypatch
):
    shown = []
    monkeypatch.setattr(
        "scorecap.app.QMessageBox.information", lambda *args: shown.append(args[2])
    )

    window.export_musicxml_with_claude_to(
        tmp_path / "Evening.musicxml", backend=LimitedClaude()
    )
    qtbot.waitUntil(lambda: not window.is_transcribing, timeout=30_000)

    assert shown and "10:10" in shown[0]


def test_after_the_limit_the_next_export_carries_on_where_it_stopped(
    window, tmp_path, qtbot, monkeypatch
):
    monkeypatch.setattr("scorecap.app.QMessageBox.information", lambda *args: None)
    monkeypatch.setattr(window, "ask_resume", lambda: True)
    claude = LimitedClaude()
    target = tmp_path / "Evening.musicxml"

    for _ in range(2):
        window.export_musicxml_with_claude_to(target, backend=claude)
        qtbot.waitUntil(lambda: not window.is_transcribing, timeout=30_000)

    assert claude.sessions == [None, "s-stopped"]
    assert target.exists()


def test_declining_to_carry_on_or_start_over_starts_nothing(
    window, tmp_path, qtbot, monkeypatch
):
    monkeypatch.setattr("scorecap.app.QMessageBox.information", lambda *args: None)
    claude = LimitedClaude()
    window.export_musicxml_with_claude_to(tmp_path / "Evening.musicxml", backend=claude)
    qtbot.waitUntil(lambda: not window.is_transcribing, timeout=30_000)
    monkeypatch.setattr(window, "ask_resume", lambda: None)

    window.export_musicxml_with_claude_to(tmp_path / "Evening.musicxml", backend=claude)

    assert not window.is_transcribing
    assert claude.sessions == [None]


def test_the_status_line_says_how_often_claude_had_to_magnify(window):
    from scorecap.reader import Progress

    reached = Progress(
        1, 4, 3, 3, zoomed=("system-01-zoom-1.png", "system-01-zoom-2.png",
                             "system-03-zoom-1.png")
    )

    assert window.zoom_text(reached) == "3 magnified pieces in 2 of 3 systems"
