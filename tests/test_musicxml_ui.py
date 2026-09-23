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
