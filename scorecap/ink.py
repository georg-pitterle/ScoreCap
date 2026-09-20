"""Where the ink sits: profiles of an image, and the staff lines in it.

Where a whole row or column has to be summed, the image is squashed to one
pixel with a box filter, which averages it in C.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PIL import Image

DARK = 128  # below this a pixel counts as ink

# A run of ink that may be broken by a gap of up to three pixels: printed and
# scanned staff lines fray, and a notehead or barline never breaks them.
_RUN = re.compile(rb"\xff(?:\xff|\x00{1,3}(?=\xff))*")


@dataclass(frozen=True)
class Line:
    """One staff line: the rows it covers, and how far it reaches."""

    top: int
    bottom: int
    left: int
    right: int

    @property
    def centre(self) -> float:
        return (self.top + self.bottom) / 2.0


def binary(grey: Image.Image) -> Image.Image:
    """White where there is ink, black where there is paper."""
    return grey.point(lambda value: 255 if value < DARK else 0)


def rows(image: Image.Image) -> bytes:
    """How much ink each row of the image holds, 0 to 255."""
    return image.resize((1, image.height), Image.BOX).tobytes()


def columns(image: Image.Image) -> bytes:
    """How much ink each column of the image holds, 0 to 255."""
    return image.resize((image.width, 1), Image.BOX).tobytes()


def staff_lines(ink: Image.Image, span: float) -> list[Line]:
    """The staff lines of a binary image, top to bottom.

    Only rows covered by ink across at least `span` of the width are looked
    at - staff lines, not notes or text. In each, the longest run of ink is
    the line itself, so a mark that merely crosses that height before or
    after it, like a divisi arrow, is left out. A line is thin and never
    quite straight, so each pixel row holds only a piece of it: consecutive
    rows make one line, and it reaches as far as any of them.
    """
    width = ink.width
    pixels = ink.tobytes()
    lines: list[Line] = []
    for y, level in enumerate(rows(ink)):
        if level < span * 255:
            continue
        row = pixels[y * width : (y + 1) * width]
        run = max(
            _RUN.finditer(row),
            key=lambda match: match.end() - match.start(),
            default=None,
        )
        if run is None or run.end() - run.start() < span * width:
            continue
        previous = lines[-1] if lines else None
        if previous is not None and y == previous.bottom + 1:
            lines[-1] = Line(
                top=previous.top,
                bottom=y,
                left=min(previous.left, run.start()),
                right=max(previous.right, run.end()),
            )
        else:
            lines.append(Line(top=y, bottom=y, left=run.start(), right=run.end()))
    return lines
