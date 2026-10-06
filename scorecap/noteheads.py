"""A system's image in, noteheads and barlines per staff out, as pitch hints."""

from __future__ import annotations

import bisect
import logging
import re
from dataclasses import dataclass
from typing import Sequence

from PIL import Image, ImageChops, ImageFilter

from .ink import Staff, binary, columns, staff_lines, staves_of

log = logging.getLogger(__name__)

LINE_SPAN = 0.5         # a staff line runs across at least half the system
HEAD_SIZE = 0.28        # radius of the opening that keeps heads, in spaces
HOLE_SIZE = 0.6         # a hollow head's hole closes under this, in spaces
HOLLOW_BELOW = 0.6      # a head's core inked less than this is open
BARLINE_COVER = 0.97    # a barline inks its column across the whole staff
STEPS = "CDEFGAB"
# The note on the bottom line of each clef, counted in diatonic steps from C0.
BOTTOM_LINE = {"G": 2 + 7 * 4, "G8": 2 + 7 * 3, "F": 4 + 7 * 2}  # E4, E3, G2

_RUN = re.compile(rb"\xff+")


@dataclass(frozen=True)
class Head:
    """A notehead: where it sits across, and its height in half spaces.

    Step 0 is the bottom line, 1 the space above it, -1 the space below.
    """

    x: int
    step: int
    hollow: bool


@dataclass(frozen=True)
class StaffReading:
    """One staff of a system: its heads, and the x of each barline."""

    top: int
    space: float
    heads: tuple[Head, ...]
    barlines: tuple[int, ...]

    def bars(self) -> list[tuple[Head, ...]]:
        """The heads bar by bar; a staff without barlines is one bar.

        A bar without heads stays in - a bar of rest still counts - but
        nothing after the closing barline is a bar.
        """
        bars: list[list[Head]] = [[] for _ in range(len(self.barlines) + 1)]
        for head in self.heads:
            bars[bisect.bisect_left(self.barlines, head.x)].append(head)
        if len(bars) > 1 and not bars[-1]:
            bars.pop()
        return [tuple(bar) for bar in bars]


def pitch_name(step: int, clef: str) -> str:
    """The note a head at `step` reads as under `clef`, without accidental."""
    index = BOTTOM_LINE[clef] + step
    return f"{STEPS[index % 7]}{index // 7}"


def _odd(size: float) -> int:
    return max(3, int(size) // 2 * 2 + 1)


def _without_staff_lines(ink: Image.Image, staff: Staff) -> Image.Image:
    """The staff's lines taken out wherever nothing crosses them.

    A pixel of the line stays if there is ink just above or just below it:
    there a notehead or a stem runs through, and cutting it would split the
    head in two.
    """
    for line in staff.lines:
        top, bottom = line.top, line.bottom + 1
        if top < 1 or bottom >= ink.height:
            continue
        band = ink.crop((0, top, ink.width, bottom))
        above = ink.crop((0, top - 1, ink.width, top))
        below = ink.crop((0, bottom, ink.width, bottom + 1))
        crossed = ImageChops.lighter(above, below).resize(band.size)
        ink.paste(ImageChops.darker(band, crossed), (0, top))
    return ink


def _blobs(ink: Image.Image) -> list[tuple[int, int, int, int]]:
    """Bounding boxes of the connected patches of ink, left, top, right, bottom.

    Joined run by run rather than pixel by pixel: after the opening only the
    heads are left, a few hundred runs where a page has millions of pixels.
    """
    width = ink.width
    pixels = ink.tobytes()
    parent: dict[int, int] = {}
    boxes: dict[int, list[int]] = {}

    def root(label: int) -> int:
        while parent[label] != label:
            parent[label] = parent[parent[label]]
            label = parent[label]
        return label

    previous: list[tuple[int, int, int]] = []
    for y in range(ink.height):
        current = []
        for match in _RUN.finditer(pixels, y * width, (y + 1) * width):
            start, end = match.start() - y * width, match.end() - y * width
            label = len(parent)
            parent[label] = label
            boxes[label] = [start, y, end, y + 1]
            for left, right, other in previous:
                if left < end and start < right:
                    a, b = root(label), root(other)
                    if a != b:
                        parent[b] = a
                        box, merged = boxes[a], boxes.pop(b)
                        boxes[a] = [
                            min(box[0], merged[0]),
                            min(box[1], merged[1]),
                            max(box[2], merged[2]),
                            max(box[3], merged[3]),
                        ]
            current.append((start, end, label))
        previous = current
        for index, (start, end, label) in enumerate(previous):
            previous[index] = (start, end, root(label))
            box = boxes[root(label)]
            box[2] = max(box[2], end)
            box[3] = y + 1
    return [tuple(box) for label, box in boxes.items() if root(label) == label]


def _ink_share(ink: Image.Image, box: tuple[int, int, int, int]) -> float:
    left, top, right, bottom = box
    if right <= left or bottom <= top:
        return 1.0
    return sum(columns(ink.crop(box))) / (255 * (right - left))


def _heads(
    clean: Image.Image, staves: Sequence[Staff], space: float
) -> list[list[Head]]:
    """Every head on the system, sorted to the staff it sits nearest."""
    hole = _odd(HOLE_SIZE * space)
    closed = clean.filter(ImageFilter.MaxFilter(hole)).filter(
        ImageFilter.MinFilter(hole)
    )
    kernel = _odd(2 * HEAD_SIZE * space)
    heads_only = closed.filter(ImageFilter.MinFilter(kernel)).filter(
        ImageFilter.MaxFilter(kernel)
    )
    found: list[list[Head]] = [[] for _ in staves]
    for left, top, right, bottom in _blobs(heads_only):
        height, width = bottom - top, right - left
        if not 0.6 * space < height < 2.6 * space:
            continue
        if not 0.8 * space < width < 1.9 * space:
            continue
        middle = (top + bottom) / 2
        nearest = min(
            range(len(staves)),
            key=lambda i: abs(middle - (staves[i].top + staves[i].bottom) / 2),
        )
        staff = staves[nearest]
        if abs(middle - (staff.top + staff.bottom) / 2) > 4 * space:
            continue
        core = (
            left + width // 4,
            top + height // 4,
            right - width // 4,
            bottom - height // 4,
        )
        hollow = _ink_share(clean, core) < HOLLOW_BELOW
        # Two heads a second apart stack into one tall patch.
        centres = (
            [top + space / 2, bottom - space / 2] if height > 1.4 * space else [middle]
        )
        bottom_line = staff.lines[-1].centre
        for y in centres:
            step = round((bottom_line - y) / (space / 2))
            found[nearest].append(Head((left + right) // 2, step, hollow))
    for heads in found:
        heads.sort(key=lambda head: (head.x, -head.step))
    return found


def _barlines(
    ink: Image.Image, staff: Staff, heads: Sequence[Head]
) -> tuple[int, ...]:
    """Columns inked from the top line to the bottom one, away from any head.

    A stem may span the staff too, but it always has its head beside it. The
    line at the very start of the staff opens the system and divides nothing.
    """
    space = staff.space
    profile = columns(ink.crop((0, staff.top, ink.width, staff.bottom + 1)))
    lines: list[int] = []
    run: list[int] = []
    for x, level in enumerate([*profile, 0]):
        if level >= BARLINE_COVER * 255:
            run.append(x)
            continue
        if run:
            centre = (run[0] + run[-1]) // 2
            run = []
            if centre <= staff.left + space:
                continue
            if any(abs(centre - head.x) < space * 1.2 for head in heads):
                continue
            lines.append(centre)
    return tuple(lines)


def read_staves(image: Image.Image) -> list[StaffReading]:
    """The staves of one system, top to bottom, with heads and barlines."""
    ink = binary(image.convert("L"))
    grown = ink.filter(ImageFilter.MaxFilter(3))  # sagging lines join up again
    staves = staves_of(staff_lines(grown, LINE_SPAN))
    if not staves:
        return []
    space = sum(staff.space for staff in staves) / len(staves)
    clean = ink.copy()
    for staff in staves:
        _without_staff_lines(clean, staff)
    heads = _heads(clean, staves, space)
    return [
        StaffReading(
            top=staff.top,
            space=staff.space,
            heads=tuple(found),
            barlines=_barlines(ink, staff, found),
        )
        for staff, found in zip(staves, heads)
    ]


def candidates(reading: StaffReading, clef: str) -> list[list[str]]:
    """The pitches the heads of each bar read as under `clef`."""
    return [[pitch_name(head.step, clef) for head in bar] for bar in reading.bars()]


def hints(images: Sequence[Image.Image]) -> str:
    """What the heads say, system by system, for a reader that knows the clefs.

    The clefs are not read here, so each head is given as it reads under
    the treble and the bass clef: `B4/D3`. A trailing `o` marks an open
    head (half or whole note), `*` a filled one. `|` is a barline.
    """
    out = []
    for number, image in enumerate(images, start=1):
        readings = read_staves(image)
        log.info("system %d: %d staves", number, len(readings))
        out.append(f"system {number}:")
        for index, reading in enumerate(readings, start=1):
            bars = [
                "-" if not bar else " ".join(
                    f"{pitch_name(h.step, 'G')}/{pitch_name(h.step, 'F')}"
                    f"{'o' if h.hollow else '*'}"
                    for h in bar
                )
                for bar in reading.bars()
            ]
            out.append(f"  staff {index}: " + " | ".join(bars))
    return "\n".join(out)
