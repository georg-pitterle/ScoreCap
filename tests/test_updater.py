"""The updater must stay silent whenever it cannot do its job."""

import pytest

from scorecap.updater import REPO_URL, PendingUpdate, UpdateService


class FakeAsset:
    def __init__(self, version: str) -> None:
        self.Version = version


class FakeInfo:
    def __init__(self, version: str) -> None:
        self.TargetFullRelease = FakeAsset(version)


class FakeManager:
    """Stands in for velopack.UpdateManager."""

    def __init__(self, info=None, current="0.1.0", error: Exception | None = None):
        self._info = info
        self._current = current
        self._error = error
        self.downloaded: list = []
        self.restarted: list = []

    def get_current_version(self):
        return self._current

    def check_for_updates(self):
        if self._error:
            raise self._error
        return self._info

    def download_updates(self, info):
        self.downloaded.append(info)

    def apply_updates_and_restart(self, info):
        self.restarted.append(info)


def service_with(manager) -> UpdateService:
    return UpdateService(manager_factory=lambda: manager)


def failing_service(error: Exception) -> UpdateService:
    def factory():
        raise error

    return UpdateService(manager_factory=factory)


def test_repo_url_points_at_the_project():
    assert REPO_URL == "https://github.com/georg-pitterle/ScoreCap"


def test_running_from_source_is_not_an_error():
    # Velopack raises exactly this when the app is not an installed bundle.
    service = failing_service(RuntimeError("This application is not properly installed"))
    assert service.is_available() is False
    assert service.check() is None
    assert service.current_version() is None


def test_no_update_available_returns_none():
    service = service_with(FakeManager(info=None))
    assert service.is_available() is True
    assert service.check() is None


def test_available_update_is_reported_with_its_version():
    manager = FakeManager(info=FakeInfo("0.2.0"))
    update = service_with(manager).check()
    assert isinstance(update, PendingUpdate)
    assert update.version == "0.2.0"


def test_a_failing_check_is_swallowed():
    # No network, GitHub down, rate limited: never interrupt the user.
    service = service_with(FakeManager(error=OSError("no network")))
    assert service.check() is None


def test_applying_downloads_first_then_restarts():
    manager = FakeManager(info=FakeInfo("0.2.0"))
    service = service_with(manager)
    update = service.check()
    assert service.apply(update) is True
    assert manager.downloaded == [update.raw]
    assert manager.restarted == [update.raw]


def test_a_failing_apply_reports_false_instead_of_raising():
    class Broken(FakeManager):
        def download_updates(self, info):
            raise OSError("download interrupted")

    manager = Broken(info=FakeInfo("0.2.0"))
    service = service_with(manager)
    update = service.check()
    assert service.apply(update) is False
    assert manager.restarted == []


def test_current_version_comes_from_the_manager():
    assert service_with(FakeManager(current="1.4.2")).current_version() == "1.4.2"


def test_the_real_factory_is_used_by_default():
    # Constructed without a fake, the service targets velopack and finds no
    # installation in the test environment - but does not blow up.
    service = UpdateService()
    assert service.is_available() is False
    assert service.check() is None
