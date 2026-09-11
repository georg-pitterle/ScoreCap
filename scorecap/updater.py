"""Self-update against the project's GitHub releases.

Velopack does the hard part - replacing a running application - but it only
works inside an installed bundle. Started from the source tree it raises, and
so do network failures. Every one of those cases has to end in silence: this
is a tool for copying sheet music, not a place for update error dialogs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

REPO_URL = "https://github.com/georg-pitterle/ScoreCap"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PendingUpdate:
    version: str
    raw: object  # velopack UpdateInfo, passed back untouched


def _velopack_manager(repo_url: str, prerelease: bool):
    import velopack

    return velopack.UpdateManager(velopack.GithubSource(repo_url, None, prerelease))


class UpdateService:
    """Checks for and applies updates, or quietly does nothing."""

    def __init__(
        self,
        repo_url: str = REPO_URL,
        prerelease: bool = False,
        manager_factory: Callable[[], object] | None = None,
    ) -> None:
        self._factory = manager_factory or (
            lambda: _velopack_manager(repo_url, prerelease)
        )
        self._manager: object | None = None
        self._tried = False

    def _get_manager(self):
        if not self._tried:
            self._tried = True
            try:
                self._manager = self._factory()
            except Exception as error:  # not installed, or velopack missing
                log.info("updates unavailable: %s", error)
                self._manager = None
        return self._manager

    def is_available(self) -> bool:
        return self._get_manager() is not None

    def current_version(self) -> str | None:
        manager = self._get_manager()
        if manager is None:
            return None
        try:
            return str(manager.get_current_version())
        except Exception as error:
            log.info("could not read the installed version: %s", error)
            return None

    def check(self) -> PendingUpdate | None:
        manager = self._get_manager()
        if manager is None:
            return None
        try:
            info = manager.check_for_updates()
        except Exception as error:
            log.info("update check failed: %s", error)
            return None
        if info is None:
            return None
        return PendingUpdate(version=str(info.TargetFullRelease.Version), raw=info)

    def apply(self, update: PendingUpdate) -> bool:
        """Download and restart into the new version. True if it got that far."""
        manager = self._get_manager()
        if manager is None or update is None:
            return False
        try:
            manager.download_updates(update.raw)
            manager.apply_updates_and_restart(update.raw)
        except Exception as error:
            log.warning("update could not be applied: %s", error)
            return False
        return True
