"""Find where a system's staff lines begin and end.

Engravers set some marks after the end of a system - the divisi arrows that
announce a split into more staves, for instance - and some before its start:
a brace or bracket that groups staves. A capture includes them, so scaled
edge to edge its staff lines start or end short of every other system on the
page. Knowing where the lines really run lets the layout put both ends on the
margins and let the marks hang outside.
"""

from __future__ import annotations

import statistics
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageFilter

from .model import Shot

DARK = 128            # below this a pixel counts as ink
LINE_SPAN = 0.5       # a staff line runs across at least half the capture
MIN_STAFF_ROWS = 5    # one staff has five lines; fewer is not a system


def _longest_run_end(row: bytes) -> tuple[int, int]:
    """Length and end (exclusive) of the longest run of ink in one pixel row."""
    best, best_end, start = 0, 0, None
    for x, value in enumerate(row + b"\x00"):
        if value and start is None:
            start = x
        elif not value and start is not None:
            if x - start > best:
                best, best_end = x - start, x
            start = None
    return best, best_end


def staff_extent(image: Image.Image) -> tuple[int, int] | None:
    """x of the first and just past the last pixel of the staff lines.

    None if there is no staff. Only rows mostly covered by ink are examined -
    staff lines, not notes or text. In each, the longest continuous run is
    the line itself, so a mark that merely crosses that height before or
    after it, like an arrow, is ignored. A line on paper is thin and sags a
    little, so each pixel row holds only a piece of it; grown by a pixel up
    and down, the pieces merge, and a line reaches as far as any of its rows.
    """
    ink = image.convert("L").point(lambda value: 255 if value < DARK else 0)
    width, height = ink.size
    if width == 0 or height == 0:
        return None
    ink = ink.filter(ImageFilter.MaxFilter(3))
    # Squashing to one column averages each row in C: its share of ink.
    coverage = ink.resize((1, height), Image.BOX).tobytes()
    rows: list[tuple[int, int, int]] = []
    for y, level in enumerate(coverage):
        if level < LINE_SPAN * 255:
            continue
        length, end = _longest_run_end(ink.crop((0, y, width, y + 1)).tobytes())
        if length >= LINE_SPAN * width:
            rows.append((y, end - length, end))
    lines: list[tuple[int, int]] = []
    for index, (y, start, end) in enumerate(rows):
        if index and y == rows[index - 1][0] + 1:
            previous_start, previous_end = lines[-1]
            lines[-1] = (min(previous_start, start), max(previous_end, end))
        else:
            lines.append((start, end))
    if len(lines) < MIN_STAFF_ROWS:
        return None
    # Grown ink reaches one pixel further on either side.
    start = round(statistics.median(line[0] for line in lines)) + 1
    end = round(statistics.median(line[1] for line in lines)) - 1
    return start, end


def staff_end(image: Image.Image) -> int | None:
    """x just past the end of the staff lines, or None if there is no staff."""
    extent = staff_extent(image)
    return None if extent is None else extent[1]


@lru_cache(maxsize=256)
def _cached_extent(
    path: str, crop: tuple[int, int, int, int] | None, stamp: int
) -> tuple[int, int] | None:
    with Image.open(path) as image:
        if crop is not None:
            image = image.crop(crop)
        return staff_extent(image)


def staff_extent_of(shot: Shot) -> tuple[int, int] | None:
    """Staff extent measured in the shot's effective (cropped) pixels, cached."""
    path = Path(shot.path)
    try:
        stamp = path.stat().st_mtime_ns  # a recapture replaces the file
    except OSError:
        return None
    return _cached_extent(str(path), shot.crop, stamp)
