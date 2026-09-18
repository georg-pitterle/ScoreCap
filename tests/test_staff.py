"""Finding where a system's staff lines end, so systems can end flush."""

from pathlib import Path

from PIL import Image, ImageDraw

from scorecap.model import Shot
from scorecap.staff import MIN_STAFF_ROWS, staff_end


def system(width=1000, height=260, line_end=900, arrow=True, staves=1) -> Image.Image:
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    for staff in range(staves):
        top = 40 + staff * 100
        for line in range(5):
            y = top + line * 12
            draw.line([10, y, line_end, y], fill=0, width=2)
        draw.line([line_end, top, line_end, top + 48], fill=0, width=3)  # barline
    if arrow:
        # A divisi arrow after the system: diagonal strokes that also cross
        # the height of a staff line - they must not count as its end.
        draw.line([line_end + 12, 64, line_end + 70, 30], fill=0, width=2)
        draw.line([line_end + 12, 64, line_end + 70, 100], fill=0, width=2)
    return image


def test_the_end_of_the_staff_lines_is_found_before_an_arrow():
    end = staff_end(system(line_end=900, arrow=True))
    assert end is not None
    assert abs(end - 902) <= 3  # the barline is part of the system


def test_without_an_arrow_the_end_is_the_line_end():
    end = staff_end(system(width=905, line_end=900, arrow=False))
    assert abs(end - 902) <= 3


def test_several_staves_agree_on_one_end():
    end = staff_end(system(height=400, line_end=880, staves=3))
    assert abs(end - 882) <= 3


def test_no_staff_lines_means_no_answer():
    blank = Image.new("L", (800, 200), 255)
    ImageDraw.Draw(blank).text((20, 80), "Soprano", fill=0)
    assert staff_end(blank) is None


def test_a_single_long_rule_is_not_a_staff():
    image = Image.new("L", (800, 200), 255)
    ImageDraw.Draw(image).line([10, 100, 780, 100], fill=0, width=2)
    assert staff_end(image) is None
    assert MIN_STAFF_ROWS >= 5


def test_colour_screenshots_are_handled():
    assert staff_end(system().convert("RGB")) is not None


def test_a_shot_is_measured_inside_its_crop(tmp_path: Path):
    from scorecap.staff import staff_end_of

    path = tmp_path / "s.png"
    system(width=1000, line_end=900).save(path)
    full = Shot(path=path, width=1000, height=260)
    cropped = Shot(path=path, width=1000, height=260, crop=(100, 0, 1000, 260))
    assert abs(staff_end_of(full) - 902) <= 3
    assert abs(staff_end_of(cropped) - 802) <= 3  # relative to the crop
