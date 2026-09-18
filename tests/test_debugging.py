"""Debug runs: breakpoints in pool threads, log lines in the console."""

import logging
import sys
import types

import pytest


def test_pool_threads_are_announced_to_an_attached_debugger(monkeypatch):
    from scorecap.app import _attach_debugger_to_this_thread

    calls = []
    fake = types.SimpleNamespace(
        debug_this_thread=lambda: calls.append("attached"),
        is_client_connected=lambda: True,
    )
    monkeypatch.setitem(sys.modules, "debugpy", fake)
    _attach_debugger_to_this_thread()
    assert calls == ["attached"]


def test_a_loaded_but_unconnected_debugger_is_left_alone(monkeypatch):
    # debug_this_thread() without a client tries to connect: a 3 s stall and
    # a traceback on every pool task.
    from scorecap.app import _attach_debugger_to_this_thread

    calls = []
    fake = types.SimpleNamespace(
        debug_this_thread=lambda: calls.append("attached"),
        is_client_connected=lambda: False,
    )
    monkeypatch.setitem(sys.modules, "debugpy", fake)
    _attach_debugger_to_this_thread()
    assert calls == []


def test_without_a_debugger_nothing_happens(monkeypatch):
    from scorecap.app import _attach_debugger_to_this_thread

    monkeypatch.delitem(sys.modules, "debugpy", raising=False)
    _attach_debugger_to_this_thread()  # must not import or raise


def test_the_update_check_announces_its_thread(monkeypatch):
    from scorecap.app import _UpdateCheck

    calls = []
    fake = types.SimpleNamespace(
        debug_this_thread=lambda: calls.append("attached"),
        is_client_connected=lambda: True,
    )
    monkeypatch.setitem(sys.modules, "debugpy", fake)

    class Quiet:
        def check(self):
            return None

    _UpdateCheck(Quiet()).run()
    assert calls == ["attached"]


@pytest.fixture()
def isolated_root_logger():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers, root.level = handlers, level


def test_debug_runs_log_to_the_console(isolated_root_logger, capsys):
    from scorecap.logs import configure_console

    configure_console()
    logging.getLogger("scorecap.test").debug("update check started")
    assert "update check started" in capsys.readouterr().err


def test_console_logging_follows_the_environment(monkeypatch):
    from scorecap.logs import DEBUG_ENV, console_requested

    monkeypatch.delenv(DEBUG_ENV, raising=False)
    assert console_requested() is False
    monkeypatch.setenv(DEBUG_ENV, "1")
    assert console_requested() is True
