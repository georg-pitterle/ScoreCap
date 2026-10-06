"""Reading the short notation, and the MusicXML written from it."""

import pytest

from scorecap import transcript
from scorecap.transcript import NOTATION, TranscriptError, parse, to_musicxml

EXAMPLE = NOTATION.split("\n\n- ")[0]

CHOIR = """\
title: Evening
key: 1
voice S: Soprano, G
voice B: Bass, F

bar 4/4
S: G4:h F#4:q G4:q~
B: G2+D3:w

bar
S: G4:w
B: R

bar 3/4
S: A4:q B4:e C5:e D5:q
B: D3:h.
"""


def test_the_example_the_reader_is_shown_reads_without_complaint():
    score = parse(EXAMPLE)

    assert [voice.name for voice in score.voices] == ["Soprano", "Tenor", "Bass"]
    assert [bar.number for bar in score.bars] == [0, 1]


def test_a_bar_that_is_too_long_is_rejected_naming_the_voice_and_the_bar():
    too_long = CHOIR.replace("S: A4:q B4:e C5:e D5:q", "S: A4:q B4:q C5:e D5:q")

    with pytest.raises(TranscriptError) as caught:
        parse(too_long)

    assert "bar 3, Soprano" in str(caught.value)
    assert "3.5 beats" in str(caught.value)


def test_every_wrong_bar_is_reported_at_once():
    """A reader asked to correct itself should not be sent back for each one."""
    wrong = CHOIR.replace("G4:w", "G4:h").replace("D3:h.", "D3:h")

    with pytest.raises(TranscriptError) as caught:
        parse(wrong)

    assert len(caught.value.problems) == 2


def test_a_voice_left_out_of_a_bar_is_named():
    with pytest.raises(TranscriptError) as caught:
        parse(CHOIR.replace("B: R\n", ""))

    assert "bar 2, Bass: missing" in str(caught.value)


def test_a_token_that_is_no_note_is_named_with_its_bar():
    with pytest.raises(TranscriptError) as caught:
        parse(CHOIR.replace("D3:h.", "D3:z"))

    assert "bar 3, Bass" in str(caught.value)


def test_a_pickup_may_be_short_but_the_voices_must_agree_on_it():
    uneven = EXAMPLE.replace("T: C4:q", "T: C4:h")

    with pytest.raises(TranscriptError) as caught:
        parse(uneven)

    assert "bar 0" in str(caught.value)


def test_a_triplet_counts_two_thirds_of_its_value():
    score = parse(CHOIR.replace("B4:e C5:e", "B4:e3 C5:e3 B4:e3"))

    assert score.bars[2].sung(0) == score.bars[2].length


def test_flats_and_sharps_sound_where_they_are_written():
    assert transcript.Pitch.parse("Bb3").midi == 58
    assert transcript.Pitch.parse("F#4").midi == 66
    assert transcript.Pitch.parse("C4").midi == 60


# --- MusicXML ---------------------------------------------------------------


@pytest.fixture(scope="module")
def written():
    return to_musicxml(parse(CHOIR))


def test_the_written_musicxml_has_a_part_per_voice_and_every_bar(written):
    names = [p.findtext("part-name") for p in written.iter("score-part")]
    parts = written.findall("part")

    assert names == ["Soprano", "Bass"]
    assert [len(part.findall("measure")) for part in parts] == [3, 3]


def test_a_tie_into_the_same_pitch_sounds_as_one_note(written):
    soprano = written.findall("part")[0]
    ties = [
        (note.findtext("pitch/step"), tie.get("type"))
        for note in soprano.iter("note")
        for tie in note.findall("tie")
    ]

    assert ties == [("G", "start"), ("G", "stop")]


def test_a_chord_is_written_as_notes_that_sound_together(written):
    bass = written.findall("part")[1]
    first = bass.find("measure").findall("note")

    assert [n.find("chord") is not None for n in first] == [False, True]


def test_a_whole_bar_rest_lasts_the_whole_bar(written):
    bass = written.findall("part")[1]
    rest = bass.findall("measure")[1].find("note")
    divisions = int(bass.findtext("measure/attributes/divisions"))

    assert rest.find("rest").get("measure") == "yes"
    assert int(rest.findtext("duration")) == 4 * divisions


def test_the_time_signature_is_repeated_only_where_it_changes(written):
    soprano = written.findall("part")[0]

    assert [m.findtext("attributes/time/beats") for m in soprano] == ["4", None, "3"]


def test_a_tenor_line_is_written_with_its_octave_clef():
    tenor = to_musicxml(parse(EXAMPLE)).findall("part")[1]

    assert tenor.findtext(".//clef/clef-octave-change") == "-1"
    assert tenor.find("measure").get("implicit") == "yes"
