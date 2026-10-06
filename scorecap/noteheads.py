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
HOLE_AREA = 0.08        # an open head encloses at least this, in spaces²
STEM_REACH = 0.8        # a stem sits this close to its head's centre, in spaces
CLEF_WIDTH = 3          # spaces from the staff's start that a clef fills
WORK_SPACE = 12         # pixels between staff lines while looking for heads
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


def _enclosed(ink: Image.Image, box: tuple[int, int, int, int]) -> int:
    """How many paper pixels inside `box` the ink closes in on every side."""
    left, top, right, bottom = box
    crop = ink.crop((left - 1, top - 1, right + 1, bottom + 1))
    width, height = crop.size
    paper = {
        (x, y)
        for y in range(height)
        for x in range(width)
        if not crop.getpixel((x, y))
    }
    reached = {(x, y) for x, y in paper if x in (0, width - 1) or y in (0, height - 1)}
    frontier = list(reached)
    while frontier:
        x, y = frontier.pop()
        for near in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if near in paper and near not in reached:
                reached.add(near)
                frontier.append(near)
    return len(paper) - len(reached)


def _opened(ink: Image.Image, size: int) -> Image.Image:
    return ink.filter(ImageFilter.MinFilter(size)).filter(ImageFilter.MaxFilter(size))


def _closed(ink: Image.Image, size: int) -> Image.Image:
    return ink.filter(ImageFilter.MaxFilter(size)).filter(ImageFilter.MinFilter(size))


def _grown(box, by: int, size: tuple[int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    return (
        max(1, left - by),
        max(1, top - by),
        min(size[0] - 1, right + by),
        min(size[1] - 1, bottom + by),
    )


def _overlaps(box, others) -> bool:
    return any(
        box[0] < other[2]
        and other[0] < box[2]
        and box[1] < other[3]
        and other[1] < box[3]
        for other in others
    )


def _head_boxes(
    ink: Image.Image, clean: Image.Image, space: float
) -> list[tuple[tuple, bool]]:
    """Patches shaped like a notehead, and whether each is open.

    Filled heads are what survives an opening: stems, beams, staff lines and
    the thin marks around a head do not. An open head is a ring too thin for
    that, so it is looked for once more with its hole closed - and kept only
    if the hole is really there, or every hairpin would pass for a half note.
    The hole is looked for with the staff lines still in: a ring that sits
    on a line merges with it, and taking the line out tears the ring open.
    """
    kernel = _odd(2 * HEAD_SIZE * space)
    filled = _blobs(_opened(clean, kernel))
    # The opening rounds the head's corners off, so its box sits inside the
    # ring; grown by half the kernel it holds the whole ring again.
    reach = kernel // 2 + 1
    rings = [
        box
        for box in _blobs(_opened(_closed(clean, _odd(HOLE_SIZE * space)), kernel))
        if not _overlaps(box, filled)
        and HOLE_AREA <= _enclosed(ink, _grown(box, reach, ink.size)) / space**2 < 1
    ]
    return [(box, False) for box in filled] + [(box, True) for box in rings]


def _heads(
    ink: Image.Image, clean: Image.Image, staves: Sequence[Staff], space: float
) -> list[list[Head]]:
    """Every head on the system, sorted to the staff it sits nearest."""
    found: list[list[Head]] = [[] for _ in staves]
    for (left, top, right, bottom), hollow in _head_boxes(ink, clean, space):
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
        # Two heads a second apart stack into one tall patch. Side by side
        # they make a wide one, and are left out: a closed hairpin looks the
        # same, and the reader sees the pair in the image anyway.
        rows = (
            [top + space / 2, bottom - space / 2] if height > 1.4 * space else [middle]
        )
        bottom_line = staff.lines[-1].centre
        for y in rows:
            step = round((bottom_line - y) / (space / 2))
            found[nearest].append(Head((left + right) // 2, step, hollow))
    for heads in found:
        heads.sort(key=lambda head: (head.x, -head.step))
    return found


def _barlines(
    ink: Image.Image, top: int, bottom: int, left: int, space: float,
    heads: Sequence[Head],
) -> tuple[int, ...]:
    """Columns inked from the top line to the bottom one, but not stems.

    The stem of a chord or of a note on ledger lines spans the staff as well,
    but it sits on the side of its head; a barline keeps further away. The
    line at the very start of the staff opens the system and divides nothing.
    """
    profile = columns(ink.crop((0, top, ink.width, bottom + 1)))
    lines: list[int] = []
    run: list[int] = []
    for x, level in enumerate([*profile, 0]):
        if level >= BARLINE_COVER * 255:
            run.append(x)
            continue
        if run:
            centre = (run[0] + run[-1]) // 2
            run = []
            if centre <= left + space:
                continue
            if any(abs(centre - head.x) < STEM_REACH * space for head in heads):
                continue
            lines.append(centre)
    return tuple(lines)


def read_staves(image: Image.Image) -> list[StaffReading]:
    """The staves of one system, top to bottom, with heads and barlines.

    The work is done on a copy scaled to WORK_SPACE pixels between lines:
    the filters cost the square of their size, and a head is no clearer at
    300 dpi than at a third of it. Positions come back in the image's own
    pixels.
    """
    grey = image.convert("L")
    full_ink = binary(grey)
    full_staves = _staves(full_ink)
    if not full_staves:
        return []
    space = sum(staff.space for staff in full_staves) / len(full_staves)
    scale = min(1.0, WORK_SPACE / space)
    if scale < 1.0:
        size = (round(grey.width * scale), round(grey.height * scale))
        grey = grey.resize(size, Image.BOX)
    ink = binary(grey)
    staves = _staves(ink)
    if len(staves) != len(full_staves):
        log.info("staves lost in scaling down; reading at full size")
        ink, staves, scale = full_ink, full_staves, 1.0
    space = sum(staff.space for staff in staves) / len(staves)
    clean = ink.copy()
    for staff in staves:
        _without_staff_lines(clean, staff)
    readings = []
    heads = _heads(ink, clean, staves, space)
    for staff, full, found in zip(staves, full_staves, heads):
        # A clef curls below the staff right at its start; no note sits there.
        heads = tuple(
            Head(round(head.x / scale), head.step, head.hollow)
            for head in found
            if head.x > staff.left + CLEF_WIDTH * staff.space
        )
        readings.append(
            StaffReading(
                top=full.top,
                space=full.space,
                heads=heads,
                barlines=_barlines(
                    full_ink, full.top, full.bottom, full.left, full.space, heads
                ),
            )
        )
    return readings


def _staves(ink: Image.Image) -> list[Staff]:
    grown = ink.filter(ImageFilter.MaxFilter(3))  # sagging lines join up again
    return staves_of(staff_lines(grown, LINE_SPAN))


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
