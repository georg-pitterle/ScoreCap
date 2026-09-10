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
