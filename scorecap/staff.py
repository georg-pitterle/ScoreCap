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

from .ink import binary, staff_lines
from .model import Shot

LINE_SPAN = 0.5       # a staff line runs across at least half the capture
MIN_STAFF_ROWS = 5    # one staff has five lines; fewer is not a system


def staff_extent(image: Image.Image) -> tuple[int, int] | None:
    """x of the first and just past the last pixel of the staff lines.

    None if there is no staff. A line on paper is thin and sags a little, so
    each pixel row holds only a piece of it; grown by a pixel up and down,
    the pieces merge into one line again.
    """
    width, height = image.size
    if width == 0 or height == 0:
        return None
    grown = binary(image.convert("L")).filter(ImageFilter.MaxFilter(3))
    lines = staff_lines(grown, LINE_SPAN)
    if len(lines) < MIN_STAFF_ROWS:
        return None
    # Grown ink reaches one pixel further on either side.
    start = round(statistics.median(line.left for line in lines)) + 1
    end = round(statistics.median(line.right for line in lines)) - 1
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
