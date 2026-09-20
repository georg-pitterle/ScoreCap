"""The eraser: white rectangles painted over a capture when it is rendered.

Like the crop, an erasure is stored as coordinates rather than painted into
the file, so the original capture stays intact and every erasure can still be
taken back. The coordinates are those of the whole capture, independent of
the crop, which is why they are painted before it.
"""

from __future__ import annotations

from typing import Sequence

from PIL import Image, ImageDraw

Erasure = tuple[int, int, int, int]


def apply(image: Image.Image, erasures: Sequence[Erasure]) -> Image.Image:
    """Paint every erasure white. The image is changed in place and returned."""
    if not erasures:
        return image
    white = 255 if image.mode in ("L", "1") else (255, 255, 255)
    draw = ImageDraw.Draw(image)
    for left, top, right, bottom in erasures:
        # PIL draws both corners; a box here is half-open, as a crop box is.
        draw.rectangle((left, top, right - 1, bottom - 1), fill=white)
    return image
