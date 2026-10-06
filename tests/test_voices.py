"""Divided voices come out as lines a singer can follow."""

from scorecap.transcript import parse
from scorecap.voices import split


def lines(text: str) -> dict[str, list[str]]:
    score = split(parse(text))
    return {
        voice.name: [
            "+".join(str(p) for p in event.pitches) or "r"
            for bar in score.bars
            for event in bar.music[index]
        ]
        for index, voice in enumerate(score.voices)
    }


def midi(name: str) -> int:
    from scorecap.transcript import Pitch

    return Pitch.parse(name).midi


BASS_CHORDS = """\
voice B: Bass, F
bar 4/4
B: C3+E3+G3:w
bar
B: B2+F3+G3:w
bar
B: C3+E3+G3:w
"""


def test_a_three_note_bass_chord_becomes_three_lines_that_move_stepwise():
    split_up = lines(BASS_CHORDS)

    assert list(split_up) == ["Bass 1", "Bass 2", "Bass 3"]
    for sung in split_up.values():
        leaps = [abs(midi(a) - midi(b)) for a, b in zip(sung, sung[1:])]
        assert max(leaps) <= 2, sung


def test_the_top_line_takes_the_top_note_when_nothing_else_decides():
    split_up = lines(BASS_CHORDS)

    assert split_up["Bass 1"][0] == "G3"
    assert split_up["Bass 3"][0] == "C3"


def test_when_a_chord_thins_out_the_free_line_joins_the_nearest_note():
    thinning = """voice B: Bass, F
bar 4/4
B: C3+E3+G3:w
bar
B: E3+G3:w
"""
    split_up = lines(thinning)

    assert [sung[1] for sung in split_up.values()] == ["G3", "E3", "E3"]


def test_a_tie_survives_only_where_the_pitch_continues():
    tied = """\
voice A: Alto, G
bar 4/4
A: E4+G4:w~
bar
A: E4+A4:w
"""
    score = split(parse(tied))

    first_bar = score.bars[0]
    ties = {
        score.voices[index].name: first_bar.music[index][0].tied
        for index in range(len(score.voices))
    }
    assert ties == {"Alto 1": False, "Alto 2": True}


def test_a_voice_that_never_divides_keeps_its_name():
    assert list(lines("voice S: Soprano, G\nbar 2/4\nS: C5:h\n")) == ["Soprano"]


def test_a_rest_in_a_divided_voice_is_a_rest_in_every_line():
    rested = "voice B: Bass, F\nbar 2/4\nB: C3+G3:q r:q\n"

    assert lines(rested) == {"Bass 1": ["G3", "r"], "Bass 2": ["C3", "r"]}
