import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QKeyEvent

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


def key(code, modifiers=Qt.KeyboardModifier.NoModifier):
    return QKeyEvent(QEvent.Type.KeyPress, code, modifiers)


def mouse_press(button, point):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(point),
        QPointF(point),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )


@pytest.fixture()
def overlay(qapp):
    from scorecap.capture import SelectionOverlay

    widget = SelectionOverlay()
    widget.start()
    yield widget
    widget.hide()


def test_a_right_click_during_the_drag_drops_it_and_stays(overlay):
    seen = []
    overlay.cancelled.connect(lambda: seen.append("cancelled"))
    overlay.selected.connect(lambda rect: seen.append("selected"))
    overlay.retake.connect(lambda: seen.append("retake"))

    overlay.mousePressEvent(mouse_press(Qt.MouseButton.LeftButton, QPoint(10, 10)))
    overlay.mousePressEvent(mouse_press(Qt.MouseButton.RightButton, QPoint(50, 50)))

    assert overlay.isVisible()
    assert seen == []


def test_a_right_click_without_a_drag_asks_for_the_last_one_again(overlay):
    seen = []
    overlay.retake.connect(lambda: seen.append("retake"))
    overlay.mousePressEvent(mouse_press(Qt.MouseButton.RightButton, QPoint(50, 50)))
    assert seen == ["retake"]


def test_backspace_asks_for_the_last_one_again(overlay):
    seen = []
    overlay.retake.connect(lambda: seen.append("retake"))
    overlay.keyPressEvent(key(Qt.Key.Key_Backspace))
    assert seen == ["retake"]


def test_a_selection_can_be_made_with_the_keyboard_alone(overlay):
    got = []
    overlay.selected.connect(got.append)

    overlay.keyPressEvent(key(Qt.Key.Key_Return))
    for _ in range(10):
        overlay.keyPressEvent(key(Qt.Key.Key_Right))
        overlay.keyPressEvent(key(Qt.Key.Key_Down))
    overlay.keyPressEvent(key(Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier))
    overlay.keyPressEvent(key(Qt.Key.Key_Return))

    assert not overlay.isVisible()
    assert (got[0].width(), got[0].height()) == (101, 100)
