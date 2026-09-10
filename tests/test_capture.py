from PIL import Image
from PySide6.QtCore import QPoint, QRect

from scorecap.capture import MIN_SELECTION_PX, is_valid_selection, normalized_rect


def test_normalizes_a_rect_dragged_up_and_left():
    rect = normalized_rect(QPoint(300, 200), QPoint(100, 50))
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (100, 50, 200, 150)


def test_normalizes_a_rect_dragged_down_and_right():
    rect = normalized_rect(QPoint(10, 20), QPoint(110, 220))
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (10, 20, 100, 200)


def test_selection_must_be_big_enough_in_both_directions():
    assert is_valid_selection(QRect(0, 0, 100, 100)) is True
    assert is_valid_selection(QRect(0, 0, MIN_SELECTION_PX - 1, 100)) is False
    assert is_valid_selection(QRect(0, 0, 100, MIN_SELECTION_PX - 1)) is False
    assert is_valid_selection(QRect(0, 0, 0, 0)) is False


def test_grab_writes_a_png_and_reports_its_pixel_size(tmp_path, qapp):
    from scorecap.capture import grab

    shot = grab(QRect(0, 0, 120, 80), tmp_path)
    assert shot.path.exists()
    assert shot.path.suffix == ".png"
    with Image.open(shot.path) as image:
        assert image.size == (shot.width, shot.height)
    assert shot.width >= 120 and shot.height >= 80
