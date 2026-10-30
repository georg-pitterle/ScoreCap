from pathlib import Path

from PIL import Image

from scorecap.model import Shot
from scorecap.settings import Settings
from scorecap.shotlist import RowData, ShotList, row_data
from scorecap.theme import LIGHT


def make_shot(tmp_path: Path, width: int = 1400, height: int = 300) -> Shot:
    path = tmp_path / "a.png"
    Image.new("RGB", (width, height), (20, 20, 20)).save(path)
    return Shot(path=path, width=width, height=height)


def test_row_shows_its_number_and_effective_size(tmp_path):
    shot = make_shot(tmp_path)
    data = row_data(0, shot, Settings(), missing=False)
    assert data.number == 1
    assert data.size_label == "1400×300"
    assert data.chip is None


def test_cropped_shot_reports_the_cropped_size(tmp_path):
    shot = make_shot(tmp_path)
    cropped = Shot(path=shot.path, width=1400, height=300, crop=(0, 0, 700, 100))
    assert row_data(0, cropped, Settings(), missing=False).size_label == "700×100"


def test_low_resolution_gets_a_warning_chip_with_the_number(tmp_path):
    shot = make_shot(tmp_path, width=400, height=200)
    data = row_data(2, shot, Settings(), missing=False)
    assert data.chip_kind == "warn"
    assert data.chip.endswith("dpi")
    assert data.chip.split()[0].isdigit()  # the actual value, not just a word


def test_missing_file_gets_its_own_chip_and_no_thumbnail(tmp_path):
    shot = Shot(path=tmp_path / "gone.png", width=1000, height=500)
    data = row_data(0, shot, Settings(), missing=True)
    assert data.chip == "File missing"
    assert data.chip_kind == "missing"
    assert data.path is None


def test_list_keeps_a_tooltip_for_every_row(qapp, tmp_path):
    widget = ShotList(LIGHT)
    widget.add_row(row_data(0, make_shot(tmp_path), Settings(), missing=False))
    assert "Capture 1" in widget.item(0).toolTip()
    assert widget.count() == 1


def test_rows_paint_without_a_thumbnail_file(qapp):
    from PySide6.QtCore import QRect, QSize
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QStyleOptionViewItem

    widget = ShotList(LIGHT)
    widget.add_row(RowData(1, "100×50", "Datei fehlt", "missing", None))
    pixmap = QPixmap(QSize(240, 64))
    painter = QPainter(pixmap)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 240, 64)
    widget.itemDelegate().paint(painter, option, widget.model().index(0, 0))
    painter.end()


def test_the_thumbnail_shows_only_the_cropped_part(qapp, tmp_path):
    from scorecap.shotlist import ShotDelegate

    # White page with a black system in its lower half only.
    image = Image.new("RGB", (1400, 1200), "white")
    image.paste((0, 0, 0), (100, 800, 1300, 1000))
    path = tmp_path / "band.png"
    image.save(path)
    shot = Shot(path=path, width=1400, height=1200, crop=(100, 800, 1300, 1000))
    data = row_data(0, shot, Settings(), missing=False)
    assert data.crop == (100, 800, 1300, 1000)
    thumb = ShotDelegate(LIGHT)._thumbnail(data.path, data.crop).toImage()
    centre = thumb.pixelColor(thumb.width() // 2, thumb.height() // 2)
    assert centre.lightness() < 50


def test_a_row_says_which_page_its_capture_landed_on(qapp, tmp_path):
    data = row_data(0, make_shot(tmp_path), Settings(), missing=False, page=2)
    widget = ShotList(LIGHT)
    widget.add_row(data)
    assert "page 2" in widget.item(0).toolTip()


def test_the_thumbnail_starts_at_the_clef_end_of_the_system(qapp):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPainter, QPixmap, Qt

    from scorecap.shotlist import ShotDelegate

    # White with a black start, the way a clef and first bar stand out.
    wide = Image.new("RGB", (1400, 100), "white")
    wide.paste((0, 0, 0), (0, 0, 60, 100))
    delegate = ShotDelegate(LIGHT)
    delegate._thumbnail = lambda *args: _pixmap(wide)
    target = QPixmap(96, 48)
    target.fill(Qt.white)
    painter = QPainter(target)
    delegate._paint_thumbnail(
        painter, QRect(0, 0, 96, 48), RowData(1, "1400×100", None, None, "wide")
    )
    painter.end()
    assert target.toImage().pixelColor(4, 24).lightness() < 50


def _pixmap(image: Image.Image):
    from PySide6.QtGui import QImage, QPixmap

    raw = image.tobytes()
    return QPixmap.fromImage(
        QImage(raw, image.width, image.height, image.width * 3, QImage.Format_RGB888)
    )
