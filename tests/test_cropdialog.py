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


def test_dialog_buttons_speak_german(tmp_path, qapp):
    from PySide6.QtWidgets import QPushButton

    from scorecap.cropdialog import CropDialog

    path = tmp_path / "a.png"
    Image.new("RGB", (200, 100), (0, 0, 0)).save(path)
    dialog = CropDialog(Shot(path=path, width=200, height=100))
    labels = {b.text() for b in dialog.findChildren(QPushButton)}
    assert "Abbrechen" in labels
    assert "Übernehmen" in labels
    assert not any(label in {"Cancel", "OK"} for label in labels)
