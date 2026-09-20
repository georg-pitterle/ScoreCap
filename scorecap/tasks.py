"""Work that must not hold up the window: update checks and scan imports.

Each task reports through signals the window owns. A QRunnable is not a
QObject and nothing keeps its Python wrapper alive once the pool has it, so
signals owned by the task itself can be collected mid-run - the result then
vanishes with "Signal source has been deleted".
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QCoreApplication, QObject, QRunnable, Signal

from .scan import ImportResult, import_scans
from .updater import PendingUpdate, UpdateService

log = logging.getLogger(__name__)


class UpdateSignals(QObject):
    found = Signal(object)
    done = Signal(object, bool)
    finished = Signal()


class ScanSignals(QObject):
    progress = Signal(str)
    done = Signal(object)
    finished = Signal()


def _attach_debugger_to_this_thread() -> None:
    """Let breakpoints fire in a Qt pool thread.

    debugpy only traces threads Python's threading module started; Qt's
    QThreadPool threads are invisible to it, so a breakpoint in a task's run()
    would never hit. Outside a debug session debugpy is not loaded and this
    does nothing.
    """
    debugpy = sys.modules.get("debugpy")
    if debugpy is None:
        return
    try:
        # Without a connected client, debug_this_thread() tries to connect
        # itself: a stall of several seconds and a traceback per task.
        if debugpy.is_client_connected():
            debugpy.debug_this_thread()
    except Exception:  # noqa: BLE001 - a debugging aid must never break the app
        pass


def emit(signal, *args) -> None:
    """Deliver a result unless the window is already gone."""
    try:
        signal.emit(*args)
    except RuntimeError:
        log.info("window closed before a background result arrived")


class BackgroundTask(QRunnable):
    """One job on a pool thread, reported on the UI thread.

    Whatever the job raises is logged rather than let out: an exception
    leaving run() takes the whole process with it. `finished` is emitted in
    every case, so the window can let the task go.
    """

    def __init__(self, signals: QObject) -> None:
        super().__init__()
        self.signals = signals

    def run(self) -> None:
        _attach_debugger_to_this_thread()
        try:
            self._work()
        except BaseException:  # noqa: BLE001 - logged, never raised into Qt
            log.exception("%s crashed", type(self).__name__)
            self._failed()
        emit(self.signals.finished)

    def _work(self) -> None:
        raise NotImplementedError

    def _failed(self) -> None:
        """What to report when the job never got to report for itself."""


class UpdateCheck(BackgroundTask):
    """Asks GitHub for a newer release without holding up the window."""

    def __init__(self, service: UpdateService, signals: UpdateSignals) -> None:
        super().__init__(signals)
        self._service = service

    def _work(self) -> None:
        log.info("update check started")
        update = self._service.check()
        found = update.version if update else "up to date"
        log.info("update check finished: %s", found)
        if update is not None:
            emit(self.signals.found, update)


class UpdateDownload(BackgroundTask):
    """Fetches an update in the background; reports success either way."""

    def __init__(
        self, service: UpdateService, update: PendingUpdate, signals: UpdateSignals
    ) -> None:
        super().__init__(signals)
        self._service = service
        self._update = update

    def _work(self) -> None:
        ok = bool(self._service.download(self._update))
        emit(self.signals.done, self._update, ok)

    def _failed(self) -> None:
        emit(self.signals.done, self._update, False)


class ScanImport(BackgroundTask):
    """Cleans scanned pages and cuts them into systems, off the UI thread."""

    def __init__(
        self, paths: Sequence[Path], target_dir: Path, signals: ScanSignals
    ) -> None:
        super().__init__(signals)
        self._paths = list(paths)
        self._target_dir = target_dir
        self._cancelled = threading.Event()
        self.stopped = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def _work(self) -> None:
        log.info("scan import of %d file(s) started", len(self._paths))
        self._report(
            import_scans(
                self._paths,
                self._target_dir,
                progress=lambda text: emit(self.signals.progress, text),
                cancelled=self._cancelled.is_set,
            )
        )

    def _failed(self) -> None:
        aborted = QCoreApplication.translate("MainWindow", "The import was aborted.")
        self._report(ImportResult([], 0, [], [], [aborted]))

    def _report(self, result: ImportResult) -> None:
        # Set before the result goes out: closing waits on it to know that
        # nothing is being written into the session folder any more.
        self.stopped.set()
        log.info("scan import finished: %d shot(s)", len(result.shots))
        emit(self.signals.done, result)
