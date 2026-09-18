"""Document state: the ordered list of captured shots, plus undo."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Shot:
    path: Path
    width: int
    height: int
    crop: tuple[int, int, int, int] | None = None
    # A scanned system, kept in grey; the export decides on black and white.
    scan: bool = False

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("shot size must be positive")
        if self.crop is None:
            return
        left, top, right, bottom = self.crop
        if left < 0 or top < 0 or right > self.width or bottom > self.height:
            raise ValueError("crop outside of image bounds")
        if right <= left or bottom <= top:
            raise ValueError("crop must have positive area")

    @property
    def effective_size(self) -> tuple[int, int]:
        if self.crop is None:
            return self.width, self.height
        left, top, right, bottom = self.crop
        return right - left, bottom - top


def normalize_move(src: int, dst: int) -> int:
    """Qt reports a drop index counted before removal; convert it to a list index."""
    return dst - 1 if dst > src else dst


class Document:
    def __init__(self) -> None:
        self._shots: list[Shot] = []
        self._history: list[list[Shot]] = []
        # Moves on every change, undo included, so "unsaved" is a comparison.
        self._revision = 0

    @property
    def shots(self) -> list[Shot]:
        return list(self._shots)

    @property
    def can_undo(self) -> bool:
        return bool(self._history)

    @property
    def revision(self) -> int:
        return self._revision

    def _snapshot(self) -> None:
        self._history.append(list(self._shots))
        self._revision += 1

    def replace_all(self, shots: list[Shot]) -> None:
        """Load a whole document; its history starts fresh."""
        self._shots = list(shots)
        self._history = []
        self._revision += 1

    def add(self, shot: Shot) -> None:
        self._snapshot()
        self._shots.append(shot)

    def extend(self, shots: list[Shot]) -> None:
        """Append several shots - one import - as a single undo step."""
        self._snapshot()
        self._shots.extend(shots)

    def remove(self, index: int) -> None:
        self._snapshot()
        del self._shots[index]

    def move(self, src: int, dst: int) -> None:
        self._snapshot()
        shot = self._shots.pop(src)
        self._shots.insert(dst, shot)

    def replace_shot(self, index: int, shot: Shot) -> None:
        self._snapshot()
        self._shots[index] = shot

    def set_crop(self, index: int, crop: tuple[int, int, int, int] | None) -> None:
        self._snapshot()
        self._shots[index] = replace(self._shots[index], crop=crop)

    def undo(self) -> bool:
        if not self._history:
            return False
        self._shots = self._history.pop()
        self._revision += 1
        return True
