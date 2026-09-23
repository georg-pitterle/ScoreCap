"""Transcribing a score with Audiveris, without ever starting one."""

from xml.etree import ElementTree

import pytest

from scorecap import omr


def test_a_missing_audiveris_is_reported_rather_than_guessed(monkeypatch, tmp_path):
    monkeypatch.delenv("AUDIVERIS_HOME", raising=False)
    monkeypatch.setattr(omr, "CANDIDATES", (tmp_path / "nowhere.exe",))

    with pytest.raises(omr.AudiverisMissing):
        omr.find_audiveris()


def test_an_audiveris_installed_elsewhere_is_found_through_the_environment(
    monkeypatch, tmp_path
):
    home = tmp_path / "Audiveris"
    home.mkdir()
    launcher = home / "Audiveris.exe"
    launcher.write_text("", encoding="utf-8")
    monkeypatch.setenv("AUDIVERIS_HOME", str(home))
    monkeypatch.setattr(omr, "CANDIDATES", ())

    assert omr.find_audiveris() == launcher


def score_xml(measures: int, pitch: str = "C", octave: str = "4") -> str:
    bars = "".join(
        f'<measure number="{number}"><note><pitch><step>{pitch}</step>'
        f"<octave>{octave}</octave></pitch><duration>4</duration></note></measure>"
        for number in range(1, measures + 1)
    )
    return (
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        "<part-name>Soprano</part-name></score-part></part-list>"
        f'<part id="P1">{bars}</part></score-partwise>'
    )


def test_two_movements_become_one_score_with_every_bar_of_both():
    first = ElementTree.fromstring(score_xml(2))
    second = ElementTree.fromstring(score_xml(3))

    glued = omr.glue([first, second])

    measures = glued.find(".//part").findall("measure")
    assert len(measures) == 5
    assert [m.get("number") for m in measures] == ["1", "2", "3", "4", "5"]


def voice_xml(name: str, octave_change: str | None, octave: str = "5") -> str:
    change = (
        f"<clef-octave-change>{octave_change}</clef-octave-change>"
        if octave_change
        else ""
    )
    return (
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        f"<part-name>{name}</part-name></score-part></part-list>"
        '<part id="P1"><measure number="1"><attributes><clef>'
        f"<sign>G</sign><line>2</line>{change}</clef></attributes>"
        f"<note><pitch><step>F</step><octave>{octave}</octave></pitch>"
        "<duration>4</duration></note></measure></part></score-partwise>"
    )


def octaves(score) -> list[str]:
    return [element.text for element in score.iter("octave")]


def test_a_tenor_whose_octave_clef_went_unnoticed_sounds_an_octave_lower():
    score = ElementTree.fromstring(voice_xml("Tenor", None))

    assert omr.fix_octave_clefs(score) == 1
    assert octaves(score) == ["4"]
    assert score.find(".//clef/clef-octave-change").text == "-1"


def test_a_tenor_whose_clef_already_says_so_is_left_alone():
    score = ElementTree.fromstring(voice_xml("Tenor", "-1", octave="4"))

    assert omr.fix_octave_clefs(score) == 0
    assert octaves(score) == ["4"]


def test_a_voice_without_a_name_is_never_moved_on_a_hunch():
    score = ElementTree.fromstring(voice_xml("", None))

    assert omr.fix_octave_clefs(score) == 0
    assert octaves(score) == ["5"]


def test_a_soprano_stays_where_it_was_written():
    score = ElementTree.fromstring(voice_xml("Soprano", None))

    assert omr.fix_octave_clefs(score) == 0
    assert octaves(score) == ["5"]


def stub_audiveris(*files: str):
    """An Audiveris that writes the MusicXML it was told to, and nothing else."""

    def run(launcher, source, out_dir, progress=None, timeout=1800):
        out_dir.mkdir(parents=True, exist_ok=True)
        for number, text in enumerate(files, start=1):
            (out_dir / f"score.mvt{number}.musicxml").write_text(
                text, encoding="utf-8"
            )
        return "stub"

    return run


def test_a_transcribed_score_lands_under_the_name_the_user_chose(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    target = tmp_path / "Perseus.musicxml"

    written = omr.transcribe(
        tmp_path / "score.pdf",
        target,
        tmp_path / "work",
        run=stub_audiveris(score_xml(2), score_xml(3)),
    )

    assert written == target
    score = omr.read_score(target)
    assert len(score.find(".//part").findall("measure")) == 5


def test_movements_past_the_ninth_keep_their_order(tmp_path, monkeypatch):
    """Named mvt1 … mvt12, they must not come back as 1, 10, 11, 12, 2 …"""
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    target = tmp_path / "Perseus.musicxml"

    omr.transcribe(
        tmp_path / "score.pdf",
        target,
        tmp_path / "work",
        run=stub_audiveris(*(score_xml(1, octave=str(n)) for n in range(1, 13))),
    )

    assert octaves(omr.read_score(target)) == [str(n) for n in range(1, 13)]


def test_what_is_written_out_carries_no_lyrics(tmp_path, monkeypatch):
    """The export is for listening; the words are on the paper already."""
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    target = tmp_path / "Perseus.musicxml"

    omr.transcribe(
        tmp_path / "score.pdf",
        target,
        tmp_path / "work",
        run=stub_audiveris(FULL_SCORE),
    )

    written = omr.read_score(target)
    assert written.find(".//lyric") is None
    assert written.find(".//pitch/step") is not None


def test_a_score_with_nothing_on_it_leaves_no_file_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    target = tmp_path / "Perseus.musicxml"

    with pytest.raises(omr.NothingFound):
        omr.transcribe(
            tmp_path / "score.pdf", target, tmp_path / "work", run=stub_audiveris()
        )

    assert not target.exists()


def test_a_failed_transcription_leaves_the_previous_file_intact(tmp_path, monkeypatch):
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    target = tmp_path / "Perseus.musicxml"
    target.write_text("older and still good", encoding="utf-8")

    with pytest.raises(omr.NothingFound):
        omr.transcribe(
            tmp_path / "score.pdf", target, tmp_path / "work", run=stub_audiveris()
        )

    assert target.read_text(encoding="utf-8") == "older and still good"


BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE score [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<score-partwise><part id="P1"><measure number="1">&lol3;</measure></part>
</score-partwise>"""

WITH_DOCTYPE = """<?xml version="1.0"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN"
 "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0"><part-list><score-part id="P1">
<part-name>Soprano</part-name></score-part></part-list>
<part id="P1"><measure number="1"><note><pitch><step>C</step>
<octave>4</octave></pitch><duration>4</duration></note></measure></part>
</score-partwise>"""


def test_a_score_that_would_blow_up_memory_is_refused(tmp_path):
    path = tmp_path / "bomb.musicxml"
    path.write_text(BILLION_LAUGHS, encoding="utf-8")

    with pytest.raises(ValueError):
        omr.read_score(path)


def test_an_ordinary_musicxml_doctype_is_no_reason_to_refuse(tmp_path):
    path = tmp_path / "plain.musicxml"
    path.write_text(WITH_DOCTYPE, encoding="utf-8")

    assert octaves(omr.read_score(path)) == ["4"]


def test_a_cancelled_transcription_says_so_rather_than_blaming_the_score(
    tmp_path, monkeypatch
):
    """Cancelling is not the same as finding nothing; the window says so."""
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")

    with pytest.raises(omr.Cancelled):
        omr.transcribe(
            tmp_path / "score.pdf",
            tmp_path / "Perseus.musicxml",
            tmp_path / "work",
            run=stub_audiveris(score_xml(1)),
            cancelled=lambda: True,
        )


def test_the_window_hears_about_a_finished_transcription(qapp, tmp_path, monkeypatch):
    from scorecap.tasks import MusicXmlExport, MusicXmlSignals

    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    target = tmp_path / "Perseus.musicxml"
    signals = MusicXmlSignals()
    seen = []
    signals.done.connect(seen.append)

    task = MusicXmlExport(
        tmp_path / "score.pdf",
        target,
        tmp_path / "work",
        signals,
        run=stub_audiveris(score_xml(1)),
    )
    task.run()

    assert seen == [target]


def test_a_transcription_that_fails_reports_the_reason(qapp, tmp_path, monkeypatch):
    from scorecap.tasks import MusicXmlExport, MusicXmlSignals

    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    signals = MusicXmlSignals()
    seen = []
    signals.done.connect(seen.append)

    task = MusicXmlExport(
        tmp_path / "score.pdf",
        tmp_path / "Perseus.musicxml",
        tmp_path / "work",
        signals,
        run=stub_audiveris(),
    )
    task.run()

    assert isinstance(seen[0], omr.NothingFound)


def test_a_cancelled_export_reaches_the_window_as_a_cancellation(
    qapp, tmp_path, monkeypatch
):
    from scorecap.tasks import MusicXmlExport, MusicXmlSignals

    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    signals = MusicXmlSignals()
    seen = []
    signals.done.connect(seen.append)

    task = MusicXmlExport(
        tmp_path / "score.pdf",
        tmp_path / "Perseus.musicxml",
        tmp_path / "work",
        signals,
        run=stub_audiveris(score_xml(1)),
    )
    task.cancel()
    task.run()

    assert isinstance(seen[0], omr.Cancelled)


FULL_SCORE = """<score-partwise version="4.0">
<defaults><scaling><millimeters>7</millimeters></scaling></defaults>
<credit><credit-words>Earth Song</credit-words></credit>
<part-list><score-part id="P1"><part-name>Soprano</part-name></score-part></part-list>
<part id="P1">
 <measure number="1">
  <print new-system="yes"><system-layout><system-distance>100</system-distance>
  </system-layout></print>
  <attributes><divisions>4</divisions><key><fifths>0</fifths></key>
   <time><beats>4</beats><beat-type>4</beat-type></time>
   <clef><sign>G</sign><line>2</line></clef>
   <staff-details><staff-lines>5</staff-lines></staff-details></attributes>
  <direction><direction-type><metronome><beat-unit>quarter</beat-unit>
   <per-minute>68</per-minute></metronome></direction-type>
   <sound tempo="68"/></direction>
  <direction><direction-type><words>dolce</words></direction-type></direction>
  <direction><direction-type><dynamics><f/></dynamics></direction-type>
   <sound dynamics="96"/></direction>
  <direction><direction-type><pedal type="start"/></direction-type></direction>
  <direction><direction-type><words>D.C.</words></direction-type>
   <sound dacapo="yes"/></direction>
  <harmony><root><root-step>A</root-step></root><kind>minor</kind></harmony>
  <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration>
   <type>quarter</type><stem>up</stem><beam number="1">begin</beam>
   <accidental>natural</accidental><tie type="start"/>
   <lyric number="1"><syllabic>single</syllabic><text>Doo</text></lyric>
   <notations><tied type="start"/><slur type="start" number="1"/>
    <articulations><staccato/></articulations></notations></note>
  <note><pitch><step>D</step><octave>4</octave></pitch><duration>2</duration>
   <type>eighth</type>
   <time-modification><actual-notes>3</actual-notes>
    <normal-notes>2</normal-notes></time-modification></note>
  <note><chord/><pitch><step>F</step><octave>4</octave></pitch>
   <duration>2</duration><type>eighth</type></note>
  <note><rest><display-step>B</display-step><display-octave>4</display-octave>
   </rest><duration>4</duration><type>quarter</type></note>
  <barline location="right"><bar-style>light-heavy</bar-style>
   <repeat direction="backward"/></barline>
 </measure>
 <measure number="2">
  <barline location="right"><bar-style>light-light</bar-style></barline>
 </measure>
</part></score-partwise>"""


def lean_score():
    return omr.playable_only(ElementTree.fromstring(FULL_SCORE))


def tags(score) -> set[str]:
    return {element.tag for element in score.iter()}


def test_the_notes_come_through_the_slimming_unchanged():
    lean = lean_score()

    notes = lean.find(".//part").iter("note")
    heard = [
        (n.findtext("pitch/step"), n.findtext("pitch/octave"), n.findtext("duration"))
        for n in notes
    ]
    assert heard == [
        ("C", "4", "4"),
        ("D", "4", "2"),
        ("F", "4", "2"),
        (None, None, "4"),
    ]


def test_nothing_that_only_draws_the_page_survives():
    gone = {
        "stem",
        "beam",
        "accidental",
        "notations",
        "tied",
        "slur",
        "staccato",
        "lyric",
        "harmony",
        "print",
        "system-layout",
        "staff-details",
        "defaults",
        "credit",
        "bar-style",
    }

    assert tags(lean_score()) & gone == set()


def test_a_tie_is_kept_where_the_bow_that_draws_it_is_not():
    """One binds the note to the next; the other only draws over it."""
    lean = lean_score()

    assert lean.find(".//tie") is not None
    assert lean.find(".//tied") is None


def test_a_triplet_keeps_the_arithmetic_that_shortens_it():
    lean = lean_score()

    assert lean.findtext(".//time-modification/actual-notes") == "3"
    assert lean.findtext(".//time-modification/normal-notes") == "2"


def test_a_repeat_stays_and_a_plain_bar_line_goes():
    lean = lean_score()

    barlines = list(lean.iter("barline"))
    assert len(barlines) == 1
    assert barlines[0].find("repeat") is not None


def test_a_tempo_marking_stays_and_a_word_of_advice_goes():
    lean = lean_score()

    directions = list(lean.iter("direction"))
    assert len(directions) == 2
    assert directions[0].findtext(".//per-minute") == "68"


def test_a_jump_stays_because_it_decides_which_bar_comes_next():
    lean = lean_score()

    assert [s.get("dacapo") for s in lean.iter("sound") if s.get("dacapo")] == ["yes"]


def test_a_forte_goes_although_it_carries_a_sound_of_its_own():
    """<sound dynamics="96"/> would slip past a test for any sound at all."""
    lean = lean_score()

    assert lean.find(".//dynamics") is None
    assert lean.find(".//pedal") is None


def test_a_chord_note_stays_a_chord_note():
    """Without it the two notes would sound one after the other."""
    assert lean_score().find(".//chord") is not None


def test_the_clef_and_the_time_survive_so_the_file_still_opens():
    lean = lean_score()

    assert lean.findtext(".//attributes/divisions") == "4"
    assert lean.findtext(".//attributes/clef/sign") == "G"
    assert lean.findtext(".//attributes/time/beats") == "4"


# --- how far Audiveris has got ----------------------------------------------

BOOK_LINE = (
    "INFO  [score]                      Book 560  | 5 sheets in "
    r"D:\Proggen\score.pdf"
)
SHEET_LINE = "INFO  [score#2]            StepMonitoring 98   | GRID"
CHATTER = "INFO  []                      Main 259  | Running in batch mode"


def test_audiveris_says_how_many_pages_it_is_about_to_read():
    assert omr.sheet_total(BOOK_LINE) == 5
    assert omr.sheet_total(SHEET_LINE) is None
    assert omr.sheet_total(CHATTER) is None


def test_every_line_of_chatter_names_the_page_it_belongs_to():
    assert omr.sheet_at_work(SHEET_LINE) == 2
    assert omr.sheet_at_work(CHATTER) is None
    assert omr.sheet_at_work(BOOK_LINE) is None


def test_the_window_is_told_each_time_a_new_page_is_reached(tmp_path, monkeypatch):
    """Only on a change: one page yields dozens of lines."""
    monkeypatch.setattr(omr, "find_audiveris", lambda: tmp_path / "Audiveris.exe")
    seen = []

    def run(launcher, source, out_dir, progress=None, timeout=1800):
        for line in (BOOK_LINE, SHEET_LINE, SHEET_LINE, "INFO  [score#3] | PAGE"):
            total = omr.sheet_total(line)
            sheet = omr.sheet_at_work(line)
            if progress and sheet is not None:
                progress(sheet, 5)
            del total
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "s.musicxml").write_text(score_xml(1), encoding="utf-8")
        return "stub"

    omr.transcribe(
        tmp_path / "score.pdf",
        tmp_path / "out.musicxml",
        tmp_path / "work",
        run=run,
        progress=lambda done, total: seen.append((done, total)),
    )

    assert seen == [(2, 5), (2, 5), (3, 5)]


SHEET_LIST_LINE = (
    "INFO  []                      Book 1929 | Book reaching PAGE on "
    "sheets:[#1#2#3#4#5]"
)


def test_the_list_of_pages_to_come_is_not_mistaken_for_the_page_at_work():
    """It would read as page 5 and start the count at the finish line."""
    assert omr.sheet_at_work(SHEET_LIST_LINE) is None
