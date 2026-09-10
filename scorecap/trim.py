"""Automatic removal of the white margin around a captured region."""

from __future__ import annotations

from dataclasses import replace

from PIL import Image

from .model import Shot
from .settings import Settings


def trim_box(
    image: Image.Image, threshold: int, padding: int
) -> tuple[int, int, int, int] | None:
    """Bounding box of everything darker than `threshold`, grown by `padding`.

    Returns None when the image holds no ink at all - a blank capture is
    better left alone than reduced to nothing.
    """
    grey = image.convert("L")
    # point() maps background to 0, ink to 255; getbbox() then finds the ink.
    ink = grey.point(lambda value: 0 if value >= threshold else 255)
    box = ink.getbbox()
    if box is None:
        return None
    left, top, right, bottom = box
    width, height = image.size
    return (
        max(left - padding, 0),
        max(top - padding, 0),
        min(right + padding, width),
        min(bottom + padding, height),
    )


def auto_crop(shot: Shot, settings: Settings) -> Shot:
    """Return the shot with its white margin cropped away.

    The crop is stored as a rectangle, so the original file stays untouched
    and the crop dialog can reset it.
    """
    if not settings.auto_trim or shot.crop is not None:
        return shot
    with Image.open(shot.path) as image:
        box = trim_box(image, settings.trim_threshold, settings.trim_padding_px)
    if box is None or box == (0, 0, shot.width, shot.height):
        return shot
    return replace(shot, crop=box)
