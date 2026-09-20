"""White-out rectangles: painted when a capture is rendered, never on disk."""

import pytest
from PIL import Image

from scorecap.erase import apply
from scorecap.model import Shot


def grey(width: int = 20, height: int = 10) -> Image.Image:
    return Image.new("L", (width, height), 0)


def test_without_erasures_the_image_is_untouched():
    image = grey()
    assert apply(image, ()).tobytes() == grey().tobytes()


def test_an_erasure_turns_its_rectangle_white():
    image = apply(grey(), ((2, 1, 5, 4),))
    assert image.getpixel((2, 1)) == 255
    assert image.getpixel((4, 3)) == 255
    # The far edge is exclusive, the way a crop box is.
    assert image.getpixel((5, 1)) == 0
    assert image.getpixel((2, 4)) == 0
    assert image.getpixel((1, 1)) == 0


def test_colour_images_are_painted_white_as_well():
    image = apply(Image.new("RGB", (20, 10), (0, 0, 0)), ((0, 0, 3, 3),))
    assert image.getpixel((1, 1)) == (255, 255, 255)


def test_several_erasures_all_land():
    image = apply(grey(), ((0, 0, 2, 2), (10, 5, 12, 7)))
    assert image.getpixel((1, 1)) == 255
    assert image.getpixel((11, 6)) == 255


# --- the shot carries them ---------------------------------------------------


def shot(tmp_path, **kwargs) -> Shot:
    path = tmp_path / "a.png"
    if not path.exists():
        Image.new("RGB", (200, 100), "white").save(path)
    return Shot(path=path, width=200, height=100, **kwargs)


def test_a_shot_has_no_erasures_by_default(tmp_path):
    assert shot(tmp_path).erasures == ()


def test_erasures_from_a_file_become_tuples(tmp_path):
    assert shot(tmp_path, erasures=[[1, 2, 3, 4]]).erasures == ((1, 2, 3, 4),)


def test_an_erasure_outside_the_image_is_refused(tmp_path):
    with pytest.raises(ValueError):
        shot(tmp_path, erasures=((0, 0, 201, 10),))


def test_an_empty_erasure_is_refused(tmp_path):
    with pytest.raises(ValueError):
        shot(tmp_path, erasures=((5, 5, 5, 20),))
