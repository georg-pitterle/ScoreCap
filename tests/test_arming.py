import pytest
from PySide6.QtCore import QRect


@pytest.fixture()
def window(qapp):
    from scorecap.app import MainWindow

    win = MainWindow()
    win.show()
    yield win
    win.close()


def test_arming_steps_aside_without_opening_the_overlay(window):
    window.arm_capture()
    assert window.isMinimized()
    assert not window._overlay.isVisible()
    assert window.is_armed is True


def test_the_hotkey_opens_the_overlay_after_arming(window):
    window.arm_capture()
    window.begin_capture()  # what the hotkey does
    assert window._overlay.isVisible()


def test_the_hotkey_still_works_without_arming(window):
    window.begin_capture()
    assert window.isMinimized()
    assert window._overlay.isVisible()


def test_arming_a_recapture_waits_for_the_hotkey_too(window, tmp_path):
    from PIL import Image

    from scorecap.model import Shot

    path = tmp_path / "a.png"
    Image.new("RGB", (1000, 500), (10, 10, 10)).save(path)
    window.add_shot(Shot(path=path, width=1000, height=500))
    window.shot_list.setCurrentRow(0)

    window.recapture_selected()
    assert window.isMinimized()
    assert not window._overlay.isVisible()

    window.begin_capture()
    assert window._overlay.isVisible()
    window._on_selected(QRect(0, 0, 200, 140))
    # Still a replacement, not a new shot, and the window comes back.
    assert len(window.document.shots) == 1
    assert not window.isMinimized()


def test_leaving_capture_mode_forgets_a_pending_recapture(window, tmp_path):
    from PIL import Image

    from scorecap.model import Shot

    path = tmp_path / "a.png"
    Image.new("RGB", (1000, 500), (10, 10, 10)).save(path)
    window.add_shot(Shot(path=path, width=1000, height=500))
    window.shot_list.setCurrentRow(0)

    window.recapture_selected()
    window.finish_capture()  # user comes back via the taskbar instead
    assert window.is_armed is False

    window.begin_capture()
    window._on_selected(QRect(0, 0, 200, 140))
    assert len(window.document.shots) == 2  # added, not replaced


def test_arming_shows_the_hotkey_as_a_hint(window):
    window.arm_capture()
    assert window.settings.hotkey in window._toast.text()
