"""Diagnostics that stay out of the user's way, but not out of the developer's.

The update check fails silently on purpose - nobody wants an error dialog
while photographing a score. Without a log, that same silence hides why an
installed copy never offered an update.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from pathlib import Path

LOG_NAME = "scorecap.log"
MAX_BYTES = 256_000
BACKUPS = 2

log = logging.getLogger("scorecap")


def log_path(frozen: bool | None = None, executable: str | None = None) -> Path | None:
    """Where an installed copy logs; None when running from the source tree.

    Velopack installs to <root>/current/ScoreCap.exe and replaces `current`
    on every update, so the log lives one level up where it survives.
    """
    is_frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if not is_frozen:
        return None
    exe = Path(executable or sys.executable).resolve()
    return exe.parent.parent / "logs" / LOG_NAME


def configure(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8"
        )
    except OSError:
        return  # a log is a courtesy; never fail start-up over it
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s")
    )
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # A windowed bundle has no stderr: uncaught exceptions would vanish.
    def unhandled(exc_type, exc, tb) -> None:
        log.critical("unhandled exception", exc_info=(exc_type, exc, tb))

    def unhandled_in_thread(args) -> None:
        log.critical(
            "unhandled exception in thread %s",
            args.thread,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = unhandled
    threading.excepthook = unhandled_in_thread
