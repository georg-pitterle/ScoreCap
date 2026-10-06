"""Chords in, one singable line per divided voice out."""

from __future__ import annotations

import itertools
from dataclasses import replace
from typing import Sequence

from .transcript import Event, Score, Voice

# Lines a voice can be split into before the search over every assignment
# gets slow; no choir divides further than this.
MOST_LINES = 6


def _widest(events: Sequence[Event]) -> int:
    return max((len(event.pitches) for event in events), default=1) or 1


def _strands(events: Sequence[Event]) -> list[tuple[Event, ...]]:
    """The bar taken apart into as many lines as its widest chord has notes.

    A chord narrower than that gives its notes out evenly, top to bottom:
    two notes over three lines keep the top one in two of them.
    """
    width = _widest(events)
    return [
        tuple(
            event if event.is_rest
            else replace(event, pitches=(
                event.pitches[rank * len(event.pitches) // width],
            ))
            for event in events
        )
        for rank in range(width)
    ]


def _notes(strand: Sequence[Event]) -> list[int]:
    return [event.pitches[0].midi for event in strand if not event.is_rest]


def _cost(order: Sequence[int], strands, last: dict[int, int]) -> float:
    """How far each line has to leap, plus a little for lines out of order.

    The leap decides; the rest only breaks ties, so that with nothing to
    lead from, the upper line takes the upper notes.
    """
    cost = 0.0
    heights = []
    for line, index in enumerate(order):
        notes = _notes(strands[index])
        if notes and line in last:
            cost += abs(notes[0] - last[line])
        heights.append(sum(notes) / len(notes) if notes else None)
    for upper, lower in zip(heights, heights[1:]):
        if upper is not None and lower is not None and lower - upper > 2:
            cost += 0.01
    cost += 0.001 * sum(1 for a, b in zip(order, order[1:]) if a > b)
    return cost


def _settle_ties(events: list[Event]) -> list[Event]:
    """Keep a tie only where the next note sings the same pitch on."""
    settled = []
    for event, following in itertools.zip_longest(events, events[1:]):
        if event.tied and (
            following is None or following.pitches != event.pitches
        ):
            event = replace(event, tied=False)
        settled.append(event)
    return settled


def _settled(column: list[tuple[Event, ...]]) -> list[tuple[Event, ...]]:
    """The same bars with every tie that leads nowhere taken off."""
    flat = _settle_ties([event for bar in column for event in bar])
    bars, start = [], 0
    for bar in column:
        bars.append(tuple(flat[start : start + len(bar)]))
        start += len(bar)
    return bars


def _lines(score: Score, voice: int, count: int) -> list[list[tuple[Event, ...]]]:
    """Each line's bars, the strands handed out by voice leading."""
    lines: list[list[tuple[Event, ...]]] = [[] for _ in range(count)]
    last: dict[int, int] = {}
    for bar in score.bars:
        strands = _strands(bar.music[voice])
        best = min(
            (
                order
                for order in itertools.product(range(len(strands)), repeat=count)
                if len(set(order)) == len(strands)
            ),
            key=lambda order: _cost(order, strands, last),
        )
        for line, index in enumerate(best):
            lines[line].append(strands[index])
            notes = _notes(strands[index])
            if notes:
                last[line] = notes[-1]
    return lines


def split(score: Score) -> Score:
    """The same score with every divided voice written out line by line.

    A voice that divides into three becomes "Bass 1" to "Bass 3", top to
    bottom where the music lets the order show. Which note goes to which
    line is decided by voice leading: each line takes the note nearest the
    one it sang last, because that is what the singers do.
    """
    voices: list[Voice] = []
    columns: list[list[tuple[Event, ...]]] = []
    for index, voice in enumerate(score.voices):
        count = max(_widest(bar.music[index]) for bar in score.bars)
        if count > MOST_LINES:
            raise ValueError(
                f"{voice.name} divides into {count}; at most {MOST_LINES}"
            )
        if count == 1:
            voices.append(voice)
            columns.append(_settled([bar.music[index] for bar in score.bars]))
            continue
        for number, line in enumerate(_lines(score, index, count), start=1):
            voices.append(
                replace(
                    voice, key=f"{voice.key}{number}", name=f"{voice.name} {number}"
                )
            )
            columns.append(_settled(line))
    bars = tuple(
        replace(bar, music=tuple(column[number] for column in columns))
        for number, bar in enumerate(score.bars)
    )
    return replace(score, voices=tuple(voices), bars=bars)

