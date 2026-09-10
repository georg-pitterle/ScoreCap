import pytest
from PySide6.QtCore import QRect


@pytest.fixture()
def window(qapp):
    """A shown main window, closed afterwards so no overlay window outlives it."""
    from scorecap.app import MainWindow

    win = MainWindow()
    win.show()
    yield win
    win.close()


def test_plain_capture_leaves_the_window_out_of_the_way(window):
    window.begin_capture()
    assert window.isMinimized()
    window._on_selected(QRect(0, 0, 120, 80))
    # The browser keeps the focus so the next hotkey press works right away.
    assert window.isMinimized()
    assert len(window.document.shots) == 1


def test_serial_capture_defers_the_preview_rebuild(window):
    window.begin_capture()
    for _ in range(3):
        window._on_selected(QRect(0, 0, 120, 80))
    assert len(window.document.shots) == 3
    assert window.pdf_bytes == b""  # nothing rendered while capturing
    assert window.is_dirty is True


def test_leaving_capture_mode_restores_and_rebuilds(window):
    window.begin_capture()
    window._on_selected(QRect(0, 0, 120, 80))
    window.finish_capture()
    assert not window.isMinimized()
    assert window.is_dirty is False
    assert window.pdf_bytes != b""
    assert window.preview.page_count == 1


def test_cancelling_the_overlay_brings_the_window_back(window):
    window.begin_capture()
    window._overlay.cancelled.emit()
    assert not window.isMinimized()


def test_recapture_returns_to_the_window(window):
    window.begin_capture()
    window._on_selected(QRect(0, 0, 120, 80))
    window.finish_capture()

    window.shot_list.setCurrentRow(0)
    window.recapture_selected()
    assert window.isMinimized()
    window._on_selected(QRect(0, 0, 200, 140))
    # Replacing one shot is a deliberate edit, so the window comes back.
    assert not window.isMinimized()
    assert len(window.document.shots) == 1
    assert window.is_dirty is False


def test_toast_never_takes_focus(window):
    from PySide6.QtCore import Qt

    window.begin_capture()
    window._on_selected(QRect(0, 0, 120, 80))
    flags = window._toast.windowFlags()
    assert flags & Qt.WindowDoesNotAcceptFocus
    assert window._toast.text() == "Aufnahme 1"


def test_restoring_from_the_taskbar_ends_capture_mode(window):
    window.begin_capture()
    window._on_selected(QRect(0, 0, 120, 80))
    window.showNormal()  # what clicking the taskbar button does
    assert window.is_dirty is False
    assert window.pdf_bytes != b""


def test_capture_trims_the_white_margin(window, monkeypatch, tmp_path):
    from PIL import Image, ImageDraw

    from scorecap import app as app_module
    from scorecap.model import Shot

    path = tmp_path / "grabbed.png"
    image = Image.new("RGB", (400, 200), (255, 255, 255))
    ImageDraw.Draw(image).rectangle([50, 40, 349, 159], fill=(0, 0, 0))
    image.save(path)
    monkeypatch.setattr(
        app_module, "grab", lambda rect, target: Shot(path=path, width=400, height=200)
    )

    window.begin_capture()
    window._on_selected(QRect(0, 0, 400, 200))
    shot = window.document.shots[0]
    assert shot.crop == (48, 38, 352, 162)  # two pixels of padding

    window.settings = window.settings.__class__(auto_trim=False)
    window._on_selected(QRect(0, 0, 400, 200))
    assert window.document.shots[1].crop is None
