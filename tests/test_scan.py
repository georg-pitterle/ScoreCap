"""Turning scanned pages into one clean capture per system."""

from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw

from scorecap.scan import (
    clear_edges,
    find_systems,
    finish,
    flatten_background,
    import_scans,
    load_pages,
    process_page,
    skew_angle,
)

WIDTH, HEIGHT = 1240, 1754  # A4 at 150 dpi
SPACE = 12                  # staff space
LEFT, RIGHT = 120, 1120     # where the staff lines start and end


def staff(draw: ImageDraw.ImageDraw, top: int) -> int:
    """Five lines with a few noteheads on them; returns the bottom line's y."""
    for line in range(5):
        y = top + line * SPACE
        draw.line([LEFT, y, RIGHT, y], fill=0, width=2)
    for x in range(200, RIGHT - 40, 90):
        y = top + (x // 90 % 5) * SPACE // 2 + SPACE
        draw.ellipse([x, y - 5, x + 13, y + 5], fill=0)
        draw.line([x + 12, y, x + 12, y - 38], fill=0, width=2)
    draw.line([RIGHT, top, RIGHT, top + 4 * SPACE], fill=0, width=3)
    return top + 4 * SPACE


def page(systems: list[int], *, lyrics=False, title=False, page_number=False,
         gap=130, staff_gap=70) -> tuple[Image.Image, list[tuple[int, int]]]:
    """A page of systems, each with the given number of staves.

    Staves of one system are joined by a barline at the left. Returns the
    page and each system's top and bottom staff line.
    """
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    if title:
        draw.rectangle([450, 60, 790, 100], fill=0)      # a heavy title
        draw.rectangle([900, 130, 1100, 145], fill=40)   # composer
    if page_number:
        draw.rectangle([610, 1690, 630, 1705], fill=0)
    extents = []
    y = 220
    for staves in systems:
        top = y
        bottom = top
        for number in range(staves):
            bottom = staff(draw, y)
            if lyrics:
                for x in range(200, RIGHT - 40, 90):
                    draw.rectangle([x, bottom + 22, x + 40, bottom + 32], fill=0)
            y = bottom + staff_gap
        if staves > 1:
            draw.line([LEFT, top, LEFT, bottom], fill=0, width=3)
        extents.append((top, bottom))
        y = bottom + gap
    return image, extents


def horizontal_line_sharpness(image: Image.Image) -> int:
    """How many rows are almost entirely ink - five per straight staff."""
    ink = image.convert("L").point(lambda v: 255 if v < 128 else 0)
    coverage = ink.resize((1, image.height), Image.BOX).tobytes()
    return sum(1 for level in coverage if level > 0.7 * 255)


# --- skew -------------------------------------------------------------------


@pytest.mark.parametrize("angle", [1.5, -1.5, 0.4, 0.0])
def test_skew_angle_recovers_a_rotation(angle):
    image, _ = page([1, 1, 1])
    tilted = image.rotate(angle, Image.BICUBIC, fillcolor=255)
    assert skew_angle(tilted) == pytest.approx(-angle, abs=0.1)


def test_small_limit_only_looks_near_zero():
    image, _ = page([1])
    tilted = image.rotate(3.0, Image.BICUBIC, fillcolor=255)
    assert abs(skew_angle(tilted, limit=0.5)) <= 0.5


def test_a_blank_page_is_not_rotated():
    assert skew_angle(Image.new("L", (400, 600), 255)) == 0.0


# --- background -------------------------------------------------------------


def shadowed(image: Image.Image) -> Image.Image:
    """Yellowed paper with a gutter shadow running down the left side."""
    shade = Image.new("L", image.size)
    shade.putdata(
        [max(90, 215 - max(0, 300 - x) // 2) for x in range(image.width)] * image.height
    )
    return Image.composite(image, shade, image.point(lambda v: 255 if v < 128 else 0))


def test_flatten_background_whitens_shadow_and_yellowing():
    image, extents = page([1, 1])
    flat = flatten_background(shadowed(image))
    for x in (10, 150, 600, 1200):
        assert flat.getpixel((x, 150)) >= 240
    top, _ = extents[0]
    assert flat.getpixel((600, top)) < 100  # staff lines stay dark
    assert flat.getpixel((130, top)) < 100  # also inside the shadow


def test_clear_edges_removes_a_dark_scanner_border():
    image, extents = page([1])
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 30, HEIGHT], fill=0)
    draw.rectangle([0, HEIGHT - 20, WIDTH, HEIGHT], fill=10)
    cleared = clear_edges(image)
    assert cleared.getpixel((5, 800)) == 255
    assert cleared.getpixel((600, HEIGHT - 5)) == 255
    assert cleared.getpixel((600, extents[0][0])) < 100


# --- systems ----------------------------------------------------------------


def test_single_staves_are_separate_systems():
    image, extents = page([1, 1, 1])
    systems = find_systems(image)
    assert len(systems) == 3
    for system, (top, bottom) in zip(systems, extents):
        left, upper, right, lower = system.content
        assert upper < top and lower > bottom
        assert left <= LEFT and right >= RIGHT


def test_staves_joined_by_a_barline_form_one_system():
    image, _ = page([2, 2])
    assert len(find_systems(image)) == 2


def test_lyrics_belong_to_the_system_above():
    image, extents = page([4, 4], lyrics=True, gap=160)
    systems = find_systems(image)
    assert len(systems) == 2
    lyrics_bottom = extents[0][1] + 32
    assert systems[0].content[3] >= lyrics_bottom
    assert systems[1].content[1] > lyrics_bottom


def test_bands_tile_the_page_without_overlap():
    image, _ = page([1, 2, 1])
    systems = find_systems(image)
    assert systems[0].band[1] == 0
    assert systems[-1].band[3] == HEIGHT
    for upper, lower in zip(systems, systems[1:]):
        assert upper.band[3] == lower.band[1]


def test_a_page_number_far_below_is_left_out():
    image, extents = page([1, 1], page_number=True)
    systems = find_systems(image)
    assert systems[-1].content[3] < 1690


def test_a_page_without_staves_has_no_systems():
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    ImageDraw.Draw(image).rectangle([100, 100, 800, 200], fill=0)
    assert find_systems(image) == []


# --- finishing --------------------------------------------------------------


def test_finish_black_and_white_is_one_bit():
    image, _ = page([1])
    result = finish(image, "bw")
    assert result.mode == "1"


def test_finish_grey_keeps_grey_but_whitens_paper():
    image = Image.new("L", (100, 100), 235)
    ImageDraw.Draw(image).rectangle([10, 10, 20, 20], fill=120)
    result = finish(image, "grey")
    assert result.mode == "L"
    assert result.getpixel((50, 50)) == 255
    assert 100 < result.getpixel((15, 15)) < 160


def test_unknown_mode_falls_back_to_black_and_white():
    image, _ = page([1])
    assert finish(image, "sepia").mode == "1"


# --- whole pages ------------------------------------------------------------


def test_process_page_makes_one_straight_shot_per_system(tmp_path):
    image, _ = page([1, 2, 1], lyrics=True)
    scan = shadowed(image).rotate(1.2, Image.BICUBIC, fillcolor=200)
    result = process_page(scan, "bw", tmp_path)
    assert len(result.shots) == 3
    assert result.found_staves
    for shot in result.shots:
        assert shot.crop is not None
        with Image.open(shot.path) as saved:
            assert saved.size == (shot.width, shot.height)
            assert saved.mode == "1"
            system = saved.crop(shot.crop)
        staves = 2 if shot is result.shots[1] else 1
        assert horizontal_line_sharpness(system) >= 5 * staves


def test_process_page_keeps_a_page_without_staves_whole(tmp_path):
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    ImageDraw.Draw(image).rectangle([100, 100, 800, 200], fill=0)
    result = process_page(image, "grey", tmp_path)
    assert not result.found_staves
    assert len(result.shots) == 1


def test_process_page_skips_a_blank_page(tmp_path):
    result = process_page(Image.new("L", (WIDTH, HEIGHT), 250), "bw", tmp_path)
    assert result.shots == []


# --- loading ----------------------------------------------------------------


def test_load_pages_renders_every_pdf_page(tmp_path):
    source, _ = page([1])
    png = tmp_path / "p.png"
    source.save(png)
    doc = pymupdf.open()
    for _ in range(2):
        doc.new_page(width=595, height=842).insert_image(
            pymupdf.Rect(0, 0, 595, 842), filename=str(png)
        )
    path = tmp_path / "scan.pdf"
    doc.save(path)
    doc.close()
    pages = list(load_pages(path))
    assert len(pages) == 2
    assert all(p.mode == "L" for p in pages)
    assert pages[0].width == pytest.approx(2480, abs=2)  # 300 dpi


def test_load_pages_reads_every_tiff_frame(tmp_path):
    frames = [Image.new("RGB", (200, 300), (250, 240, 200)) for _ in range(3)]
    path = tmp_path / "scan.tif"
    frames[0].save(path, save_all=True, append_images=frames[1:])
    pages = list(load_pages(path))
    assert len(pages) == 3
    assert all(p.mode == "L" and p.size == (200, 300) for p in pages)


def test_load_pages_rejects_unknown_files(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    with pytest.raises(ValueError):
        list(load_pages(path))


# --- importing ----------------------------------------------------------------


def test_import_scans_collects_shots_and_reports_odd_pages(tmp_path):
    music, _ = page([1, 1])
    text = Image.new("L", (WIDTH, HEIGHT), 255)
    ImageDraw.Draw(text).rectangle([100, 100, 800, 200], fill=0)
    blank = Image.new("L", (WIDTH, HEIGHT), 255)
    path = tmp_path / "scan.tif"
    music.save(path, save_all=True, append_images=[text, blank])
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a png")
    messages = []
    result = import_scans([path, broken], "bw", tmp_path / "out", messages.append)
    assert result.pages == 3
    assert len(result.shots) == 3  # two systems, one whole text page
    assert result.whole == ["scan.tif, Seite 2"]
    assert result.blank == ["scan.tif, Seite 3"]
    assert len(result.errors) == 1 and "broken.png" in result.errors[0]
    assert messages and "scan.tif" in messages[0]


def test_import_scans_stops_when_cancelled(tmp_path):
    music, _ = page([1])
    path = tmp_path / "scan.tif"
    music.save(path, save_all=True, append_images=[music, music])
    result = import_scans([path], "bw", tmp_path / "out", cancelled=lambda: True)
    assert result.shots == [] and result.pages == 0


def test_very_large_scans_are_scaled_down(tmp_path):
    path = tmp_path / "huge.png"
    Image.new("L", (6000, 8000), 255).save(path)
    (image,) = load_pages(path)
    assert image.width <= 3600
