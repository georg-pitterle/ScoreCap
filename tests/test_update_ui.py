"""Updates download quietly, then offer a restart; closing installs them."""

import pytest
from PySide6.QtWidgets import QMessageBox

from scorecap.updater import PendingUpdate

UPDATE = PendingUpdate(version="9.9.9", raw=object())


class RecordingService:
    """Stands in for UpdateService inside the window."""

    def __init__(self, download_ok: bool = True) -> None:
        self.download_ok = download_ok
        self.downloaded: list = []
        self.restarted: list = []
        self.on_exit: list = []

    def is_available(self):
        return True

    def check(self):
        return UPDATE

    def download(self, update):
        self.downloaded.append(update)
        return self.download_ok

    def restart_into(self, update):
        self.restarted.append(update)
        return True

    def install_on_exit(self, update):
        self.on_exit.append(update)
        return True


@pytest.fixture()
def window(qapp):
    from scorecap.app import MainWindow

    win = MainWindow()
    win.updates = RecordingService()
    win.show()
    yield win
    win.close()


def test_nothing_is_shown_before_an_update_is_found(window):
    assert window.update_button.isVisible() is False
    assert window.update_label.isVisible() is False


def test_a_found_update_starts_downloading_without_a_button(window, monkeypatch):
    started = []
    monkeypatch.setattr(window, "_start_download", lambda update: started.append(update))
    window._on_update_found(UPDATE)
    assert started == [UPDATE]
    assert window.update_button.isVisible() is False
    assert "9.9.9" in window.update_label.text()


def test_a_finished_download_offers_the_restart(window):
    window._on_update_downloaded(UPDATE, True)
    assert window.update_button.isVisible() is True
    assert "restart now" in window.update_button.text().lower()
    assert "when you close" in window.update_label.text()


def test_a_failed_download_stays_quiet(window):
    window._on_update_downloaded(UPDATE, False)
    assert window.update_button.isVisible() is False
    assert window.isVisible()


def test_restarting_without_captures_does_not_ask(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("asked"))
    window._on_update_downloaded(UPDATE, True)
    window.update_button.click()
    assert window.updates.restarted == [UPDATE]


def test_restarting_with_unsaved_captures_asks_first_and_respects_cancel(
    window, monkeypatch, tmp_path
):
    from PIL import Image

    from scorecap.model import Shot

    path = tmp_path / "a.png"
    Image.new("RGB", (400, 100), (0, 0, 0)).save(path)
    window.add_shot(Shot(path=path, width=400, height=100))

    asked = []
    monkeypatch.setattr(
        "scorecap.app.ask_save_changes",
        lambda parent: asked.append(1) or "cancel",
    )
    window._on_update_downloaded(UPDATE, True)
    window.update_button.click()
    assert asked, "restarting would discard the captures without warning"
    assert window.updates.restarted == []
    monkeypatch.setattr("scorecap.app.ask_save_changes", lambda parent: "discard")


def test_restarting_with_captures_goes_ahead_when_discarded(window, monkeypatch, tmp_path):
    from PIL import Image

    from scorecap.model import Shot

    path = tmp_path / "a.png"
    Image.new("RGB", (400, 100), (0, 0, 0)).save(path)
    window.add_shot(Shot(path=path, width=400, height=100))
    monkeypatch.setattr("scorecap.app.ask_save_changes", lambda parent: "discard")
    window._on_update_downloaded(UPDATE, True)
    window.update_button.click()
    assert window.updates.restarted == [UPDATE]


def test_closing_installs_a_downloaded_update(qapp):
    from scorecap.app import MainWindow

    win = MainWindow()
    service = RecordingService()
    win.updates = service
    win.show()
    win._on_update_downloaded(UPDATE, True)
    win.close()
    assert service.on_exit == [UPDATE]


def test_closing_without_a_downloaded_update_installs_nothing(qapp):
    from scorecap.app import MainWindow

    win = MainWindow()
    service = RecordingService()
    win.updates = service
    win.show()
    win.close()
    assert service.on_exit == []


def test_a_crashing_check_is_logged_not_lost(caplog):
    from scorecap.tasks import UpdateCheck, UpdateSignals

    class Exploding:
        def check(self):
            raise RuntimeError("velopack blew up in the worker")

    with caplog.at_level("INFO"):
        UpdateCheck(Exploding(), UpdateSignals()).run()  # must not raise
    assert "velopack blew up in the worker" in caplog.text


def test_a_crashing_download_is_logged_and_reported_as_failed(caplog):
    from scorecap.tasks import UpdateDownload, UpdateSignals

    class Exploding:
        def download(self, update):
            raise RuntimeError("disk full")

    results = []
    task = UpdateDownload(Exploding(), UPDATE, UpdateSignals())
    task.signals.done.connect(lambda update, ok: results.append(ok))
    with caplog.at_level("INFO"):
        task.run()
    assert "disk full" in caplog.text
    assert results == [False]


def test_a_result_arriving_after_the_window_closed_does_not_raise(qapp, caplog):
    from scorecap.app import MainWindow
    from scorecap.tasks import UpdateCheck, UpdateSignals

    class Service:
        def check(self):
            return UPDATE

    win = MainWindow()
    signals = UpdateSignals(win)
    task = UpdateCheck(Service(), signals)
    win.close()
    win.deleteLater()
    QApplicationLike = type(qapp)
    QApplicationLike.sendPostedEvents(None, 0)  # actually delete the window
    from PySide6.QtCore import QEvent

    QApplicationLike.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    with caplog.at_level("INFO"):
        task.run()  # emits into a deleted object; must be absorbed
