from pathlib import Path

import pytest

from scorecap.model import Document, Shot, normalize_move


def make_shot(name: str = "a.png", width: int = 100, height: int = 50) -> Shot:
    return Shot(path=Path(name), width=width, height=height)


def test_effective_size_without_crop():
    assert make_shot().effective_size == (100, 50)


def test_effective_size_with_crop():
    shot = Shot(path=Path("a.png"), width=100, height=50, crop=(10, 5, 60, 45))
    assert shot.effective_size == (50, 40)


@pytest.mark.parametrize(
    "crop",
    [(-1, 0, 50, 40), (0, 0, 101, 40), (0, 0, 0, 40), (30, 0, 10, 40)],
)
def test_invalid_crop_rejected(crop):
    with pytest.raises(ValueError):
        Shot(path=Path("a.png"), width=100, height=50, crop=crop)


def test_add_and_remove():
    doc = Document()
    doc.add(make_shot("a.png"))
    doc.add(make_shot("b.png"))
    assert [s.path.name for s in doc.shots] == ["a.png", "b.png"]
    doc.remove(0)
    assert [s.path.name for s in doc.shots] == ["b.png"]


def test_move_reorders():
    doc = Document()
    for name in ("a.png", "b.png", "c.png"):
        doc.add(make_shot(name))
    doc.move(0, 2)
    assert [s.path.name for s in doc.shots] == ["b.png", "c.png", "a.png"]


def test_set_crop_keeps_original_shot_fields():
    doc = Document()
    doc.add(make_shot())
    doc.set_crop(0, (0, 0, 50, 25))
    shot = doc.shots[0]
    assert shot.crop == (0, 0, 50, 25)
    assert (shot.width, shot.height) == (100, 50)


def test_undo_reverts_last_change():
    doc = Document()
    doc.add(make_shot("a.png"))
    doc.add(make_shot("b.png"))
    doc.remove(1)
    assert doc.can_undo is True
    assert doc.undo() is True
    assert [s.path.name for s in doc.shots] == ["a.png", "b.png"]


def test_undo_on_empty_history_returns_false():
    doc = Document()
    assert doc.can_undo is False
    assert doc.undo() is False


def test_shots_property_returns_a_copy():
    doc = Document()
    doc.add(make_shot())
    doc.shots.clear()
    assert len(doc.shots) == 1


def test_normalize_move_downward_shifts_by_one():
    assert normalize_move(0, 3) == 2
    assert normalize_move(2, 0) == 0
    assert normalize_move(1, 1) == 1


def test_every_change_moves_the_revision():
    doc = Document()
    seen = [doc.revision]
    doc.add(make_shot("a.png"))
    seen.append(doc.revision)
    doc.add(make_shot("b.png"))
    seen.append(doc.revision)
    doc.move(0, 1)
    seen.append(doc.revision)
    doc.set_crop(0, (0, 0, 10, 10))
    seen.append(doc.revision)
    doc.remove(0)
    seen.append(doc.revision)
    assert len(set(seen)) == len(seen)


def test_undo_is_a_change_too():
    doc = Document()
    doc.add(make_shot())
    before = doc.revision
    doc.undo()
    assert doc.revision != before


def test_replacing_everything_resets_the_history():
    doc = Document()
    doc.add(make_shot("a.png"))
    doc.replace_all([make_shot("x.png"), make_shot("y.png")])
    assert [s.path.name for s in doc.shots] == ["x.png", "y.png"]
    assert doc.can_undo is False  # an opened project starts a fresh history


def test_extend_adds_several_shots_as_one_undo_step():
    doc = Document()
    doc.add(make_shot("a.png"))
    doc.extend([make_shot("b.png"), make_shot("c.png")])
    assert [s.path.name for s in doc.shots] == ["a.png", "b.png", "c.png"]
    assert doc.undo() is True
    assert [s.path.name for s in doc.shots] == ["a.png"]


def test_set_edits_changes_crop_and_erasures_in_one_step():
    doc = Document()
    doc.add(make_shot())
    before = doc.revision
    doc.set_edits(0, (0, 0, 50, 25), ((1, 1, 5, 5),))
    shot = doc.shots[0]
    assert (shot.crop, shot.erasures) == ((0, 0, 50, 25), ((1, 1, 5, 5),))
    assert doc.revision != before
    assert doc.undo() is True
    assert (doc.shots[0].crop, doc.shots[0].erasures) == (None, ())
