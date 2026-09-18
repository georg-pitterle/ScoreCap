from PIL import Image
from PySide6.QtCore import QPoint, QRect, QSize

from scorecap.cropdialog import display_rect, widget_to_source
from scorecap.model import Shot


def test_wide_image_is_letterboxed_vertically():
    rect = display_rect(QSize(1000, 500), QSize(400, 400))
    assert (rect.width(), rect.height()) == (400, 200)
    assert rect.x() == 0
    assert rect.y() == 100


def test_tall_image_is_letterboxed_horizontally():
    rect = display_rect(QSize(500, 1000), QSize(400, 400))
    assert (rect.width(), rect.height()) == (200, 400)
    assert rect.x() == 100
    assert rect.y() == 0


def test_widget_point_maps_to_source_pixel():
    display = QRect(0, 100, 400, 200)
    point = widget_to_source(QPoint(200, 200), display, QSize(1000, 500))
    assert (point.x(), point.y()) == (500, 250)


def test_points_outside_the_image_are_clamped():
    display = QRect(0, 100, 400, 200)
    source = QSize(1000, 500)
    assert widget_to_source(QPoint(-50, -50), display, source) == QPoint(0, 0)
    assert widget_to_source(QPoint(9999, 9999), display, source) == QPoint(1000, 500)


def test_dialog_starts_with_the_existing_crop_and_can_reset(tmp_path, qapp):
    from scorecap.cropdialog import CropDialog

    path = tmp_path / "a.png"
    Image.new("RGB", (200, 100), (0, 0, 0)).save(path)
    shot = Shot(path=path, width=200, height=100, crop=(10, 10, 150, 90))
    dialog = CropDialog(shot)
    assert dialog.crop == (10, 10, 150, 90)
    dialog.reset()
    assert dialog.crop is None


def test_dialog_buttons_speak_german(tmp_path, qapp, german):
    from PySide6.QtWidgets import QPushButton

    from scorecap.cropdialog import CropDialog

    path = tmp_path / "a.png"
    Image.new("RGB", (200, 100), (0, 0, 0)).save(path)
    dialog = CropDialog(Shot(path=path, width=200, height=100))
    labels = {b.text() for b in dialog.findChildren(QPushButton)}
    assert "Abbrechen" in labels
    assert "Übernehmen" in labels
    assert not any(label in {"Cancel", "OK"} for label in labels)


# --- adjusting an existing crop ---------------------------------------------

from scorecap.cropdialog import adjust_crop, hit_test

SELECTION = QRect(100, 100, 200, 100)  # right edge at 300, bottom at 200


def test_corners_edges_and_inside_are_told_apart():
    assert hit_test(SELECTION, QPoint(102, 98)) == "tl"
    assert hit_test(SELECTION, QPoint(299, 201)) == "br"
    assert hit_test(SELECTION, QPoint(300, 100)) == "tr"
    assert hit_test(SELECTION, QPoint(100, 200)) == "bl"
    assert hit_test(SELECTION, QPoint(200, 101)) == "t"
    assert hit_test(SELECTION, QPoint(302, 150)) == "r"
    assert hit_test(SELECTION, QPoint(200, 150)) == "move"
    assert hit_test(SELECTION, QPoint(50, 50)) is None


def test_dragging_a_corner_moves_only_its_two_edges():
    assert adjust_crop((10, 10, 100, 60), "tl", -5, 3, (200, 100)) == (5, 13, 100, 60)
    assert adjust_crop((10, 10, 100, 60), "br", 20, 10, (200, 100)) == (10, 10, 120, 70)


def test_dragging_an_edge_moves_only_that_edge():
    assert adjust_crop((10, 10, 100, 60), "r", 30, 40, (200, 100)) == (10, 10, 130, 60)
    assert adjust_crop((10, 10, 100, 60), "t", 30, -4, (200, 100)) == (10, 6, 100, 60)


def test_edges_stay_on_the_image_and_never_cross():
    assert adjust_crop((10, 10, 100, 60), "tl", -50, -50, (200, 100)) == (0, 0, 100, 60)
    assert adjust_crop((10, 10, 100, 60), "l", 500, 0, (200, 100)) == (95, 10, 100, 60)


def test_moving_keeps_the_size_and_stays_inside():
    assert adjust_crop((10, 10, 100, 60), "move", 20, 5, (200, 100)) == (30, 15, 120, 65)
    assert adjust_crop((10, 10, 100, 60), "move", 500, 500, (200, 100)) == (110, 50, 200, 100)


def test_dragging_a_corner_in_the_dialog_keeps_the_rest(tmp_path, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from scorecap.cropdialog import CropDialog

    path = tmp_path / "a.png"
    Image.new("RGB", (400, 200), (255, 255, 255)).save(path)
    dialog = CropDialog(Shot(path=path, width=400, height=200, crop=(40, 20, 360, 180)))
    canvas = dialog._canvas
    canvas.resize(800, 400)  # two widget pixels per image pixel
    QTest.mousePress(canvas, Qt.LeftButton, pos=QPoint(720, 360))
    QTest.mouseMove(canvas, QPoint(760, 380))
    QTest.mouseRelease(canvas, Qt.LeftButton, pos=QPoint(760, 380))
    assert dialog.crop == (40, 20, 380, 190)


def test_without_a_crop_the_image_edges_can_be_dragged_in(tmp_path, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from scorecap.cropdialog import CropDialog

    path = tmp_path / "a.png"
    Image.new("RGB", (400, 200), (255, 255, 255)).save(path)
    dialog = CropDialog(Shot(path=path, width=400, height=200))
    canvas = dialog._canvas
    canvas.resize(800, 400)
    QTest.mousePress(canvas, Qt.LeftButton, pos=QPoint(0, 200))  # left edge
    QTest.mouseMove(canvas, QPoint(100, 210))
    QTest.mouseRelease(canvas, Qt.LeftButton, pos=QPoint(100, 210))
    assert dialog.crop == (50, 0, 400, 200)
    # Inside, a drag still draws a new rectangle.
    dialog.reset()
    QTest.mousePress(canvas, Qt.LeftButton, pos=QPoint(200, 100))
    QTest.mouseMove(canvas, QPoint(400, 300))
    QTest.mouseRelease(canvas, Qt.LeftButton, pos=QPoint(400, 300))
    assert dialog.crop == (100, 50, 200, 150)
