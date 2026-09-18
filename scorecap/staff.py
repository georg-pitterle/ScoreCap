"""Find where a system's staff lines end.

Engravers set some marks after the end of a system - the divisi arrows that
announce a split into more staves, for instance. A screenshot includes them,
so a capture scaled edge to edge ends its staff lines short of every other
system on the page. Knowing where the lines really end lets the layout put
that point on the right margin and let the mark hang outside it.
"""

from __future__ import annotations

import statistics
from functools import lru_cache
from pathlib import Path

from PIL import Image

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


def staff_end(image: Image.Image) -> int | None:
    """x just past the end of the staff lines, or None if there is no staff.

    Only rows mostly covered by ink are examined - staff lines, not notes or
    text. In each, the longest continuous run is the line itself, so a mark
    that merely crosses that height further right, like an arrow, is ignored.
    """
    ink = image.convert("L").point(lambda value: 255 if value < DARK else 0)
    width, height = ink.size
    if width == 0 or height == 0:
        return None
    # Squashing to one column averages each row in C: its share of ink.
    coverage = ink.resize((1, height), Image.BOX).tobytes()
    ends = []
    for y, level in enumerate(coverage):
        if level < LINE_SPAN * 255:
            continue
        length, end = _longest_run_end(ink.crop((0, y, width, y + 1)).tobytes())
        if length >= LINE_SPAN * width:
            ends.append(end)
    if len(ends) < MIN_STAFF_ROWS:
        return None
    return round(statistics.median(ends))


@lru_cache(maxsize=256)
def _cached_end(path: str, crop: tuple[int, int, int, int] | None, stamp: int) -> int | None:
    with Image.open(path) as image:
        if crop is not None:
            image = image.crop(crop)
        return staff_end(image)


def staff_end_of(shot: Shot) -> int | None:
    """Staff end measured in the shot's effective (cropped) pixels, cached."""
    path = Path(shot.path)
    try:
        stamp = path.stat().st_mtime_ns  # a recapture replaces the file
    except OSError:
        return None
    return _cached_end(str(path), shot.crop, stamp)
