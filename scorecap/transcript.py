"""Short score notation in, checked bars and MusicXML out."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Sequence
from xml.etree import ElementTree

log = logging.getLogger(__name__)

STEPS = "CDEFGAB"
SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
ALTERS = {"": 0, "n": 0, "#": 1, "##": 2, "b": -1, "bb": -2}
VALUES = {"w": Fraction(4), "h": Fraction(2), "q": Fraction(1),
          "e": Fraction(1, 2), "s": Fraction(1, 4)}
TYPES = {"w": "whole", "h": "half", "q": "quarter", "e": "eighth", "s": "16th"}
CLEFS = {"G": ("G", 2, 0), "G8": ("G", 2, -1), "F": ("F", 4, 0)}
VOICE_PROGRAM = 53  # General MIDI "Voice Oohs": a sung line, not a piano

# The contract with whoever reads the score; the reader's prompt quotes it.
NOTATION = """title: The Road Home
key: -1
tempo: 92
voice S: Soprano, G
voice T: Tenor, G8
voice B: Bass, F

bar 3/4 pickup
S: C5:q
T: C4:q
B: A3:q

bar
S: D5:q C5:q A4:q~
T: D4:q C4:h
B: G3+Bb3:h.

- `key` counts sharps (positive) or flats (negative); `tempo` is quarters per
  minute and may be left out.
- One `voice` line per staff or sung voice: a short key, its name, its clef -
  G (treble), G8 (treble sounding an octave lower, tenors) or F (bass).
- `bar` opens each bar. A time signature after it holds until the next one;
  `pickup` marks an incomplete bar, which every voice must fill equally.
- Every voice has one line in every bar.
- A token is pitch:value. Values are w h q e s (whole to sixteenth); `.` or
  `..` dots it, a trailing `3` makes it a triplet note (`e3`).
- Pitches are written as they sound, with octave: C4 is middle C. Write the
  accidental the key signature or an earlier accidental in the bar implies:
  `Bb3`, `F#4`, `Bn3` is plain B.
- `G3+Bb3:h` is a chord - two or more notes the voice divides into.
- `~` at the end ties the note to the next one of the same pitch.
- `x:` before the pitch marks a spoken or shouted note: `x:C4:q`.
- `r:q` is a rest, `R` alone a rest for the whole bar.
- `%` starts a comment line.
"""

_PITCH = re.compile(r"([A-G])(bb|b|##|#|n)?(-?\d)")
_VALUE = re.compile(r"([whqes])(\.{0,2})(3?)")
_TIME = re.compile(r"(\d+)/(\d+)")


class TranscriptError(ValueError):
    """The notation does not add up; each problem names its bar and voice."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


@dataclass(frozen=True)
class Pitch:
    step: str
    alter: int
    octave: int

    def __post_init__(self) -> None:
        if self.step not in STEPS:
            raise ValueError(f"no such note: {self.step}")
        if self.alter not in (-2, -1, 0, 1, 2):
            raise ValueError(f"no such accidental: {self.alter}")

    @classmethod
    def parse(cls, text: str) -> Pitch:
        match = _PITCH.fullmatch(text)
        if match is None:
            raise ValueError(f"not a pitch: {text!r}")
        step, accidental, octave = match.groups()
        return cls(step, ALTERS[accidental or ""], int(octave))

    @property
    def midi(self) -> int:
        return 12 * (self.octave + 1) + SEMITONES[self.step] + self.alter

    def __str__(self) -> str:
        accidental = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}[self.alter]
        return f"{self.step}{accidental}{self.octave}"


@dataclass(frozen=True)
class Event:
    """A note, a chord or a rest. No pitches is a rest; no value fills the bar."""

    pitches: tuple[Pitch, ...] = ()
    value: str = ""
    dots: int = 0
    triplet: bool = False
    tied: bool = False
    spoken: bool = False

    def __post_init__(self) -> None:
        if self.value and self.value not in VALUES:
            raise ValueError(f"no such note value: {self.value}")
        if not self.value and (self.pitches or self.dots or self.triplet):
            raise ValueError("only a rest can fill a whole bar")
        if not 0 <= self.dots <= 2:
            raise ValueError("at most two dots")
        if self.tied and not self.pitches:
            raise ValueError("a rest cannot be tied")

    @property
    def is_rest(self) -> bool:
        return not self.pitches

    @property
    def fills_bar(self) -> bool:
        return not self.value

    def duration(self, bar_length: Fraction) -> Fraction:
        """Length in quarter notes; a whole-bar rest takes the bar's."""
        if self.fills_bar:
            return bar_length
        length = VALUES[self.value] * (2 - Fraction(1, 2**self.dots))
        return length * Fraction(2, 3) if self.triplet else length


@dataclass(frozen=True)
class Voice:
    key: str
    name: str
    clef: str

    def __post_init__(self) -> None:
        if self.clef not in CLEFS:
            raise ValueError(f"no such clef: {self.clef} (G, G8 or F)")


@dataclass(frozen=True)
class Bar:
    """One bar: what each voice sings in it, in the order of the voices."""

    number: int
    time: tuple[int, int]
    music: tuple[tuple[Event, ...], ...]
    pickup: bool = False

    def __post_init__(self) -> None:
        beats, beat_type = self.time
        if beats < 1 or beat_type not in (1, 2, 4, 8, 16):
            raise ValueError(f"no such time signature: {beats}/{beat_type}")

    @property
    def length(self) -> Fraction:
        beats, beat_type = self.time
        return Fraction(4 * beats, beat_type)

    def sung(self, voice: int) -> Fraction:
        return sum(
            (event.duration(self.length) for event in self.music[voice]), Fraction(0)
        )


@dataclass(frozen=True)
class Score:
    title: str
    fifths: int
    voices: tuple[Voice, ...]
    bars: tuple[Bar, ...]
    tempo: int | None = None

    def __post_init__(self) -> None:
        if not -7 <= self.fifths <= 7:
            raise ValueError(f"no such key signature: {self.fifths}")
        if not self.voices:
            raise ValueError("a score needs at least one voice")
        if not self.bars:
            raise ValueError("a score needs at least one bar")
        for bar in self.bars:
            if len(bar.music) != len(self.voices):
                raise ValueError(f"bar {bar.number} does not have every voice")


# --- reading ------------------------------------------------------------------


def _event(token: str) -> Event:
    if token == "R":
        return Event()
    tied = token.endswith("~")
    token = token.rstrip("~")
    spoken = token.startswith("x:")
    if spoken:
        token = token[2:]
    head, sep, value = token.rpartition(":")
    match = _VALUE.fullmatch(value)
    if not sep or match is None:
        raise ValueError(f"no note value in {token!r}")
    letter, dots, triplet = match.groups()
    pitches = () if head == "r" else tuple(Pitch.parse(p) for p in head.split("+"))
    pitches = tuple(sorted(set(pitches), key=lambda p: -p.midi))
    return Event(pitches, letter, len(dots), bool(triplet), tied, spoken)


def _beats(length: Fraction) -> str:
    return str(float(length)).removesuffix(".0")


def _header(line: str, fields: dict[str, str], voices: list[Voice]) -> None:
    name, _, value = line.partition(":")
    name, value = name.strip(), value.strip()
    if name.startswith("voice "):
        label, _, clef = value.rpartition(",")
        voices.append(Voice(name[6:].strip(), label.strip(), clef.strip()))
    elif name in ("title", "key", "tempo"):
        fields[name] = value
    else:
        raise ValueError(f"unknown line {line!r}")


def parse(text: str) -> Score:
    """The score the notation describes, every bar checked against its time.

    Every problem is collected before giving up, so a reader asked to
    correct the notation hears about all of them at once.
    """
    fields: dict[str, str] = {}
    voices: list[Voice] = []
    raw: list[tuple[str, bool, dict[str, str]]] = []  # time, pickup, lines
    problems: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith(("%", "```")):
            continue
        try:
            if line == "bar" or line.startswith("bar "):
                words = line.split()[1:]
                raw.append(
                    (
                        next((w for w in words if _TIME.fullmatch(w)), ""),
                        "pickup" in words,
                        {},
                    )
                )
            elif raw:
                key, _, music = line.partition(":")
                if key.strip() in raw[-1][2]:
                    raise ValueError(f"voice {key.strip()} twice in one bar")
                raw[-1][2][key.strip()] = music.strip()
            else:
                _header(line, fields, voices)
        except ValueError as error:
            problems.append(f"line {number}: {error}")
    if not voices:
        problems.append("no voices declared")
    if not raw:
        problems.append("no bars")
    if problems:
        raise TranscriptError(problems)

    first = 0 if raw[0][1] else 1
    names = {voice.key: voice for voice in voices}
    bars: list[Bar] = []
    time: tuple[int, int] | None = None
    for index, (signature, pickup, lines) in enumerate(raw):
        number = first + index
        if signature:
            beats, beat_type = _TIME.fullmatch(signature).groups()
            time = (int(beats), int(beat_type))
        if time is None:
            problems.append(f"bar {number}: no time signature yet")
            continue
        for key in lines.keys() - names.keys():
            problems.append(f"bar {number}: no voice called {key}")
        music = []
        for voice in voices:
            if voice.key not in lines:
                problems.append(f"bar {number}, {voice.name}: missing")
                music.append(())
                continue
            try:
                music.append(tuple(_event(t) for t in lines[voice.key].split()))
            except ValueError as error:
                problems.append(f"bar {number}, {voice.name}: {error}")
                music.append(())
        try:
            bars.append(Bar(number, time, tuple(music), pickup))
        except ValueError as error:
            problems.append(f"bar {number}: {error}")
            continue
        problems += _length_problems(bars[-1], voices)
    try:
        score = Score(
            fields.get("title", ""),
            int(fields.get("key", "0")),
            tuple(voices),
            tuple(bars),
            int(fields["tempo"]) if fields.get("tempo") else None,
        )
    except ValueError as error:
        problems.append(str(error))
    if problems:
        raise TranscriptError(problems)
    return score


def _length_problems(bar: Bar, voices: Sequence[Voice]) -> list[str]:
    """What is wrong with how long each voice sings in this bar.

    A pickup may be shorter than its time signature, but all voices still
    have to agree on how much shorter - else they drift apart from here on.
    """
    problems = []
    sung = [bar.sung(index) for index in range(len(voices))]
    for voice, events, length in zip(voices, bar.music, sung):
        if not events:
            continue
        if any(e.fills_bar for e in events) and len(events) > 1:
            problems.append(
                f"bar {bar.number}, {voice.name}: R must stand alone in its bar"
            )
        elif bar.pickup and length > bar.length:
            problems.append(
                f"bar {bar.number}, {voice.name}: {_beats(length)} beats in a "
                f"pickup to {bar.time[0]}/{bar.time[1]}"
            )
        elif not bar.pickup and length != bar.length:
            problems.append(
                f"bar {bar.number}, {voice.name}: {_beats(length)} beats where "
                f"{bar.time[0]}/{bar.time[1]} holds {_beats(bar.length)}"
            )
    if bar.pickup and len({s for s, e in zip(sung, bar.music) if e}) > 1:
        problems.append(f"bar {bar.number}: the voices disagree on the pickup")
    return problems


# --- writing ------------------------------------------------------------------


def _sub(parent: ElementTree.Element, tag: str, text: object = None, **attrib: str):
    element = ElementTree.SubElement(parent, tag, attrib)
    if text is not None:
        element.text = str(text)
    return element


def _divisions(score: Score) -> int:
    """Ticks per quarter note that measure every note in the score exactly."""
    divisions = 1
    for bar in score.bars:
        for events in bar.music:
            for event in events:
                divisions = math.lcm(divisions, event.duration(bar.length).denominator)
    return divisions


def _attributes(measure, score: Score, voice: Voice, bar: Bar, first: bool) -> None:
    attributes = _sub(measure, "attributes")
    if first:
        _sub(attributes, "divisions", _divisions(score))
        key = _sub(attributes, "key")
        _sub(key, "fifths", score.fifths)
    time = _sub(attributes, "time")
    _sub(time, "beats", bar.time[0])
    _sub(time, "beat-type", bar.time[1])
    if first:
        sign, line, octave = CLEFS[voice.clef]
        clef = _sub(attributes, "clef")
        _sub(clef, "sign", sign)
        _sub(clef, "line", line)
        if octave:
            _sub(clef, "clef-octave-change", octave)


def _note(measure, event: Event, pitch: Pitch | None, chord: bool, ticks: int,
          ties: tuple[bool, bool]) -> None:
    note = _sub(measure, "note")
    if chord:
        _sub(note, "chord")
    if pitch is None:
        _sub(note, "rest", **({"measure": "yes"} if event.fills_bar else {}))
    else:
        written = _sub(note, "pitch")
        _sub(written, "step", pitch.step)
        if pitch.alter:
            _sub(written, "alter", pitch.alter)
        _sub(written, "octave", pitch.octave)
    _sub(note, "duration", ticks)
    stops, starts = ties
    if stops:
        _sub(note, "tie", type="stop")
    if starts:
        _sub(note, "tie", type="start")
    _sub(note, "voice", 1)
    if not event.fills_bar:
        _sub(note, "type", TYPES[event.value])
        for _ in range(event.dots):
            _sub(note, "dot")
    if event.triplet:
        modification = _sub(note, "time-modification")
        _sub(modification, "actual-notes", 3)
        _sub(modification, "normal-notes", 2)
    if event.spoken:
        _sub(note, "notehead", "x")
    if stops or starts:
        notations = _sub(note, "notations")
        if stops:
            _sub(notations, "tied", type="stop")
        if starts:
            _sub(notations, "tied", type="start")


def _part(root, score: Score, index: int, voice: Voice) -> None:
    part = _sub(root, "part", id=f"P{index + 1}")
    divisions = _divisions(score)
    flat = [event for bar in score.bars for event in bar.music[index]]
    position = 0
    for number, bar in enumerate(score.bars):
        measure = _sub(
            part,
            "measure",
            number=str(bar.number),
            **({"implicit": "yes"} if bar.pickup else {}),
        )
        if number == 0 or bar.time != score.bars[number - 1].time:
            _attributes(measure, score, voice, bar, number == 0)
        if number == 0 and score.tempo and index == 0:
            direction = _sub(measure, "direction", placement="above")
            kind = _sub(direction, "direction-type")
            metronome = _sub(kind, "metronome")
            _sub(metronome, "beat-unit", "quarter")
            _sub(metronome, "per-minute", score.tempo)
            _sub(direction, "sound", tempo=str(score.tempo))
        for event in bar.music[index]:
            before = flat[position - 1] if position else None
            after = flat[position + 1] if position + 1 < len(flat) else None
            ticks = int(event.duration(bar.length) * divisions)
            for order, pitch in enumerate(event.pitches or (None,)):
                ties = (
                    bool(before and before.tied and pitch in before.pitches),
                    bool(event.tied and after and pitch in after.pitches),
                )
                _note(measure, event, pitch, order > 0, ticks, ties)
            position += 1


def to_musicxml(score: Score) -> ElementTree.Element:
    """The score as MusicXML, one part per voice.

    A tie is written only where the next note carries the same pitch on: a
    bow into a different note is a slur, and a slur does not sound.
    """
    root = ElementTree.Element("score-partwise", version="4.0")
    if score.title:
        work = _sub(root, "work")
        _sub(work, "work-title", score.title)
    part_list = _sub(root, "part-list")
    for index, voice in enumerate(score.voices):
        ident = f"P{index + 1}"
        score_part = _sub(part_list, "score-part", id=ident)
        _sub(score_part, "part-name", voice.name)
        instrument = _sub(score_part, "score-instrument", id=f"{ident}-I1")
        _sub(instrument, "instrument-name", voice.name)
        midi = _sub(score_part, "midi-instrument", id=f"{ident}-I1")
        channel = index % 15 + 1
        # Channel 10 is the drum kit; a voice there would play as percussion.
        _sub(midi, "midi-channel", channel + 1 if channel >= 10 else channel)
        _sub(midi, "midi-program", VOICE_PROGRAM)
    for index, voice in enumerate(score.voices):
        _part(root, score, index, voice)
    return root
