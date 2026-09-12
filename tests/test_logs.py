"""Silent towards the user must not mean invisible towards the developer."""

import logging
from pathlib import Path

import pytest

from scorecap.logs import LOG_NAME, configure, log_path


def test_no_log_file_when_running_from_source():
    assert log_path(frozen=False) is None


def test_installed_copy_logs_beside_its_versions(tmp_path):
    exe = tmp_path / "ScoreCap" / "current" / "ScoreCap.exe"
    assert log_path(frozen=True, executable=str(exe)) == (
        tmp_path / "ScoreCap" / "logs" / LOG_NAME
    )


@pytest.fixture()
def isolated_root_logger():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in root.handlers:
        if handler not in handlers:
            handler.close()
    root.handlers, root.level = handlers, level


def test_configure_writes_records_to_the_file(tmp_path, isolated_root_logger):
    target = tmp_path / "logs" / LOG_NAME
    configure(target)
    logging.getLogger("scorecap.test").info("update check: available=%s", True)
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert "update check: available=True" in target.read_text(encoding="utf-8")


def test_configure_tolerates_an_unwritable_location(isolated_root_logger):
    configure(Path("Z:/does-not-exist/logs/scorecap.log"))  # must not raise


def test_configure_without_a_path_does_nothing(isolated_root_logger):
    before = list(logging.getLogger().handlers)
    configure(None)
    assert logging.getLogger().handlers == before
