from pathlib import Path

import pytest

from scorecap.model import Document, Shot


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


def test_editing_a_shot_keeps_its_other_fields():
    doc = Document()
    doc.add(make_shot())
    doc.set_edits(0, (0, 0, 50, 25), ((10, 10, 20, 20),))
    shot = doc.shots[0]
    assert shot.crop == (0, 0, 50, 25)
    assert shot.erasures == ((10, 10, 20, 20),)
    assert (shot.width, shot.height) == (100, 50)


def test_undo_reverts_last_change():
    doc = Document()
    doc.add(make_shot("a.png"))
    doc.add(make_shot("b.png"))
    doc.remove(1)
    assert doc.undo() is True
    assert [s.path.name for s in doc.shots] == ["a.png", "b.png"]


def test_undo_on_empty_history_returns_false():
    doc = Document()
    assert doc.undo() is False


def test_replacing_everything_resets_the_history():
    doc = Document()
    doc.add(make_shot("a.png"))
    doc.replace_all([make_shot("x.png"), make_shot("y.png")])
    assert [s.path.name for s in doc.shots] == ["x.png", "y.png"]
    # An opened project starts a fresh history: nothing to undo into.
    assert doc.undo() is False


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


def _three():
    doc = Document()
    for name in "abc":
        doc.add(Shot(path=Path(f"{name}.png"), width=10, height=10))
    return doc


def _names(doc):
    return [shot.path.stem for shot in doc.shots]


def test_redo_brings_back_what_undo_took():
    doc = _three()
    doc.undo()
    assert doc.redo() is True
    assert _names(doc) == ["a", "b", "c"]


def test_a_new_change_ends_what_can_be_redone():
    doc = _three()
    doc.undo()
    doc.remove(0)
    assert doc.can_redo is False
    assert doc.redo() is False


def test_redo_counts_as_a_change_for_the_save_question():
    doc = _three()
    doc.undo()
    before = doc.revision
    doc.redo()
    assert doc.revision != before


def test_several_captures_go_in_one_undo_step():
    doc = _three()
    doc.remove_many([0, 2])
    assert _names(doc) == ["b"]
    doc.undo()
    assert _names(doc) == ["a", "b", "c"]


def test_arranging_takes_only_a_true_order():
    doc = _three()
    doc.arrange([2, 0, 1])
    assert _names(doc) == ["c", "a", "b"]
    with pytest.raises(ValueError):
        doc.arrange([0, 0, 1])


def test_a_block_moves_together_and_keeps_its_gap():
    from scorecap.model import shifted_order

    assert shifted_order(5, [1, 3], 1) == [0, 2, 1, 4, 3]
    assert shifted_order(5, [1, 2], -1) == [1, 2, 0, 3, 4]


def test_a_block_at_the_edge_stays_where_it_is():
    from scorecap.model import shifted_order

    assert shifted_order(3, [0, 2], -1) is None
    assert shifted_order(3, [0, 2], 1) is None
    assert shifted_order(3, [], 1) is None
