"""Document state: the ordered list of captured shots, plus undo."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class Shot:
    path: Path
    width: int
    height: int
    crop: tuple[int, int, int, int] | None = None
    # A scanned system, kept in grey; the export decides on black and white.
    scan: bool = False
    # Rectangles the eraser whites out, in the coordinates of the whole image.
    erasures: tuple[tuple[int, int, int, int], ...] = ()

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("shot size must be positive")
        # A project file hands us lists; store them as tuples so shots compare.
        object.__setattr__(self, "erasures", tuple(tuple(e) for e in self.erasures))
        for box in (self.crop, *self.erasures):
            self._check_box(box)

    def _check_box(self, box: tuple[int, int, int, int] | None) -> None:
        if box is None:
            return
        left, top, right, bottom = box
        if left < 0 or top < 0 or right > self.width or bottom > self.height:
            raise ValueError("box outside of image bounds")
        if right <= left or bottom <= top:
            raise ValueError("box must have positive area")

    @property
    def effective_size(self) -> tuple[int, int]:
        if self.crop is None:
            return self.width, self.height
        left, top, right, bottom = self.crop
        return right - left, bottom - top


@dataclass(frozen=True)
class PageSource:
    """The scanned page a capture was cut from, and where it sat on it.

    A cut between two systems can fall in the wrong place, and the band the
    import saved then holds half a system. The page is what the editing
    dialog needs to take such a cut back; it lives only as long as the
    session, so nothing of this is written to a project.
    """

    page: Shot
    region: tuple[int, int, int, int]


def shifted_order(count: int, rows: Sequence[int], step: int) -> list[int] | None:
    """The order after moving `rows` one place up (-1) or down (+1) as a block.

    None when one of them already stands at that end: a block squeezed
    against the edge would close its gaps, which is not what was asked for.
    """
    chosen = set(rows)
    if not chosen or (step < 0 and 0 in chosen) or (step > 0 and count - 1 in chosen):
        return None
    order = list(range(count))
    for row in sorted(chosen, reverse=step > 0):
        order[row], order[row + step] = order[row + step], order[row]
    return order


class Document:
    def __init__(self) -> None:
        self._shots: list[Shot] = []
        self._history: list[list[Shot]] = []
        self._future: list[list[Shot]] = []  # what undo took back, for redo
        # Moves on every change, undo included, so "unsaved" is a comparison.
        self._revision = 0

    @property
    def shots(self) -> list[Shot]:
        return list(self._shots)

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def can_undo(self) -> bool:
        return bool(self._history)

    @property
    def can_redo(self) -> bool:
        return bool(self._future)

    def _snapshot(self) -> None:
        self._history.append(list(self._shots))
        self._future = []
        self._revision += 1

    def replace_all(self, shots: list[Shot]) -> None:
        """Load a whole document; its history starts fresh."""
        self._shots = list(shots)
        self._history = []
        self._future = []
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

    def remove_many(self, indices: Sequence[int]) -> None:
        """Delete several captures as a single undo step."""
        self._snapshot()
        for index in sorted(set(indices), reverse=True):
            del self._shots[index]

    def move(self, src: int, dst: int) -> None:
        self._snapshot()
        shot = self._shots.pop(src)
        self._shots.insert(dst, shot)

    def arrange(self, order: Sequence[int]) -> None:
        """Put the captures in `order`, a list of their present rows."""
        if sorted(order) != list(range(len(self._shots))):
            raise ValueError(f"not an order of {len(self._shots)} rows: {order}")
        self._snapshot()
        self._shots = [self._shots[row] for row in order]

    def replace_shot(self, index: int, shot: Shot) -> None:
        self._snapshot()
        self._shots[index] = shot

    def set_edits(
        self,
        index: int,
        crop: tuple[int, int, int, int] | None,
        erasures: tuple[tuple[int, int, int, int], ...],
    ) -> None:
        """What one visit to the edit dialog changed - a single undo step."""
        self._snapshot()
        self._shots[index] = replace(self._shots[index], crop=crop, erasures=erasures)

    def undo(self) -> bool:
        if not self._history:
            return False
        self._future.append(self._shots)
        self._shots = self._history.pop()
        self._revision += 1
        return True

    def redo(self) -> bool:
        if not self._future:
            return False
        self._history.append(self._shots)
        self._shots = self._future.pop()
        self._revision += 1
        return True
