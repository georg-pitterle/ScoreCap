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
