"""Noteheads on a drawn staff read as the pitches they show."""

import pytest
from PIL import Image, ImageDraw

from scorecap.noteheads import candidates, hints, read_staves

SPACE = 20
BOTTOM = 140  # y of the bottom line of the first staff


def draw_staff(draw: ImageDraw.ImageDraw, bottom: int, width: int) -> None:
    for line in range(5):
        y = bottom - line * SPACE
        draw.rectangle((20, y - 1, width - 20, y), fill=0)


def draw_head(draw, x: int, step: int, bottom: int, hollow: bool = False) -> None:
    y = bottom - step * SPACE / 2
    box = (x - 12, y - 9, x + 12, y + 9)
    draw.ellipse(box, fill=0)
    if hollow:
        draw.ellipse((x - 8, y - 5, x + 8, y + 5), fill=255)
    draw.rectangle((x + 10, y - 70, x + 11, y), fill=0)  # stem


def draw_barline(draw, x: int, bottom: int) -> None:
    draw.rectangle((x - 1, bottom - 4 * SPACE - 1, x + 1, bottom), fill=0)


@pytest.fixture(scope="module")
def system() -> Image.Image:
    """Two staves: E4 and A4 | an open C5, over G2+B2 | a lone D3 (bass)."""
    image = Image.new("L", (640, 340), 255)
    draw = ImageDraw.Draw(image)
    lower = BOTTOM + 160
    for bottom in (BOTTOM, lower):
        draw_staff(draw, bottom, 640)
        draw_barline(draw, 20, bottom)
        draw_barline(draw, 320, bottom)
        draw_barline(draw, 619, bottom)
    draw_head(draw, 100, 0, BOTTOM)
    draw_head(draw, 180, 3, BOTTOM)
    draw_head(draw, 420, 5, BOTTOM, hollow=True)
    draw_head(draw, 120, 0, lower)
    draw_head(draw, 120, 2, lower)
    draw_head(draw, 420, 4, lower)
    return image


@pytest.fixture(scope="module")
def staves(system):
    return read_staves(system)


def test_a_drawn_staff_yields_the_pitches_it_shows(staves):
    upper, lower = staves

    assert candidates(upper, "G") == [["E4", "A4"], ["C5"]]
    assert candidates(lower, "F") == [["B2", "G2"], ["D3"]]


def test_an_open_head_is_told_from_a_filled_one(staves):
    upper = staves[0]

    assert [head.hollow for head in upper.heads] == [False, False, True]


def test_a_tenor_staff_reads_an_octave_below_the_treble(staves):
    upper = staves[0]

    assert candidates(upper, "G8") == [["E3", "A3"], ["C4"]]


def test_the_hints_give_each_head_under_both_clefs_bar_by_bar(system):
    text = hints([system])

    assert "staff 1: E4/G2* A4/C3* | C5/E3o" in text
    assert "staff 2:" in text


def test_a_blank_image_has_no_staves():
    assert read_staves(Image.new("L", (300, 100), 255)) == []
