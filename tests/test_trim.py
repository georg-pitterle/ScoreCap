from pathlib import Path

from PIL import Image, ImageDraw

from scorecap.model import Shot
from scorecap.settings import Settings
from scorecap.trim import auto_crop, trim_box


def white(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), (255, 255, 255))


def with_ink(box: tuple[int, int, int, int], size=(200, 100), fill=(0, 0, 0)):
    image = white(*size)
    ImageDraw.Draw(image).rectangle([box[0], box[1], box[2] - 1, box[3] - 1], fill=fill)
    return image


def test_white_border_is_trimmed_away():
    image = with_ink((40, 20, 160, 80))
    assert trim_box(image, threshold=245, padding=0) == (40, 20, 160, 80)


def test_padding_is_added_around_the_ink():
    image = with_ink((40, 20, 160, 80))
    assert trim_box(image, threshold=245, padding=5) == (35, 15, 165, 85)


def test_padding_is_clamped_to_the_image():
    image = with_ink((2, 1, 198, 99))
    assert trim_box(image, threshold=245, padding=10) == (0, 0, 200, 100)


def test_blank_image_is_not_trimmed():
    assert trim_box(white(200, 100), threshold=245, padding=0) is None


def test_ink_reaching_every_edge_keeps_the_full_image():
    image = with_ink((0, 0, 200, 100))
    assert trim_box(image, threshold=245, padding=0) == (0, 0, 200, 100)


def test_near_white_counts_as_background_but_light_grey_does_not():
    almost_white = with_ink((40, 20, 160, 80), fill=(250, 250, 250))
    assert trim_box(almost_white, threshold=245, padding=0) is None

    light_grey = with_ink((40, 20, 160, 80), fill=(200, 200, 200))
    assert trim_box(light_grey, threshold=245, padding=0) == (40, 20, 160, 80)


def test_auto_crop_sets_the_crop_on_the_shot(tmp_path: Path):
    path = tmp_path / "a.png"
    with_ink((40, 20, 160, 80)).save(path)
    shot = Shot(path=path, width=200, height=100)
    trimmed = auto_crop(shot, Settings(trim_padding_px=0))
    assert trimmed.crop == (40, 20, 160, 80)
    assert trimmed.effective_size == (120, 60)
    assert trimmed.path == shot.path  # the file itself is untouched


def test_auto_crop_is_skipped_when_switched_off(tmp_path: Path):
    path = tmp_path / "a.png"
    with_ink((40, 20, 160, 80)).save(path)
    shot = Shot(path=path, width=200, height=100)
    assert auto_crop(shot, Settings(auto_trim=False)).crop is None


def test_auto_crop_leaves_a_blank_shot_alone(tmp_path: Path):
    path = tmp_path / "blank.png"
    white(200, 100).save(path)
    shot = Shot(path=path, width=200, height=100)
    assert auto_crop(shot, Settings()).crop is None


def test_auto_crop_keeps_an_existing_manual_crop(tmp_path: Path):
    path = tmp_path / "a.png"
    with_ink((40, 20, 160, 80)).save(path)
    shot = Shot(path=path, width=200, height=100, crop=(0, 0, 50, 50))
    assert auto_crop(shot, Settings()).crop == (0, 0, 50, 50)


# --- the crop after erasing ---------------------------------------------------


def page_with_a_number(tmp_path: Path) -> Shot:
    """A system in the middle and a page number up in the right corner."""
    image = white(200, 100)
    draw = ImageDraw.Draw(image)
    draw.rectangle([50, 40, 149, 59], fill=(0, 0, 0))     # the system
    draw.rectangle([180, 10, 194, 19], fill=(0, 0, 0))    # the page number
    path = tmp_path / "page.png"
    image.save(path)
    return auto_crop(Shot(path=path, width=200, height=100), Settings())


def test_erasing_a_mark_at_the_edge_tightens_the_crop(tmp_path):
    from dataclasses import replace

    from scorecap.trim import crop_after_erasing

    shot = page_with_a_number(tmp_path)
    assert shot.crop == (48, 8, 197, 62)  # the number pulls the crop out
    erased = replace(shot, erasures=((178, 8, 197, 22),))
    assert crop_after_erasing(erased, Settings()) == (48, 38, 152, 62)


def test_the_crop_never_grows_back_over_what_was_cropped_away(tmp_path):
    from dataclasses import replace

    from scorecap.trim import crop_after_erasing

    shot = page_with_a_number(tmp_path)
    # A crop the user pulled in by hand, leaving the page number outside.
    tight = replace(shot, crop=(60, 45, 140, 55), erasures=((0, 0, 20, 20),))
    left, top, right, bottom = crop_after_erasing(tight, Settings())
    assert (left, top, right, bottom) == (60, 45, 140, 55)


def test_without_auto_trim_the_crop_is_left_alone(tmp_path):
    from dataclasses import replace

    from scorecap.trim import crop_after_erasing

    shot = page_with_a_number(tmp_path)
    erased = replace(shot, erasures=((178, 8, 197, 22),))
    assert crop_after_erasing(erased, Settings(auto_trim=False)) == shot.crop


def test_erasing_everything_leaves_the_crop_as_it_was(tmp_path):
    """A capture rubbed out completely is better kept than reduced to nothing."""
    from dataclasses import replace

    from scorecap.trim import crop_after_erasing

    shot = page_with_a_number(tmp_path)
    erased = replace(shot, erasures=((0, 0, 200, 100),))
    assert crop_after_erasing(erased, Settings()) == shot.crop
