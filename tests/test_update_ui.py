"""The update hint sits in the status bar and never blocks the window."""

import pytest

from scorecap.updater import PendingUpdate


@pytest.fixture()
def window(qapp):
    from scorecap.app import MainWindow

    win = MainWindow()
    win.show()
    yield win
    win.close()


def test_no_hint_before_an_update_is_found(window):
    assert window.update_button.isVisible() is False


def test_finding_an_update_shows_a_restart_button(window):
    window._on_update_found(PendingUpdate(version="9.9.9", raw=object()))
    assert window.update_button.isVisible() is True
    assert "9.9.9" in window.update_button.text()


def test_the_button_applies_the_update(window, monkeypatch):
    applied = []
    update = PendingUpdate(version="9.9.9", raw=object())
    monkeypatch.setattr(
        window.updates, "apply", lambda u: applied.append(u) or True
    )
    window._on_update_found(update)
    window.update_button.click()
    assert applied == [update]


def test_a_failed_apply_leaves_the_window_usable(window, monkeypatch):
    monkeypatch.setattr(window.updates, "apply", lambda u: False)
    window._on_update_found(PendingUpdate(version="9.9.9", raw=object()))
    window.update_button.click()
    assert window.isVisible()
    assert "fehlgeschlagen" in window.status.text().lower()


def test_checking_runs_off_the_ui_thread(window):
    from PySide6.QtCore import QRunnable

    assert isinstance(window._update_check_task(), QRunnable)


def test_a_crashing_check_is_logged_not_lost(caplog):
    from scorecap.app import _UpdateCheck

    class Exploding:
        def check(self):
            raise RuntimeError("velopack blew up in the worker")

    with caplog.at_level("INFO"):
        _UpdateCheck(Exploding()).run()  # must not raise out of the thread
    assert "velopack blew up in the worker" in caplog.text
