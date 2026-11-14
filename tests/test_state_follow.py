from __future__ import annotations

from notes_prompter.notes import Deck
from notes_prompter.state import Controller


def make_deck(name: str, n: int) -> Deck:
    return Deck(name=name, path=f"{name}.pptx", notes=tuple(f"{name}{i}" for i in range(1, n + 1)))


def test_follow_sets_active_deck_and_index():
    ctrl = Controller()
    ctrl.follow(make_deck("charla", 3), 2)
    msg = ctrl.current_message()
    assert (msg["presentation"], msg["index"], msg["notes"]) == ("charla", 2, "charla2")


def test_follow_with_out_of_range_index_falls_back_to_first_slide():
    ctrl = Controller()
    ctrl.follow(make_deck("charla", 3), 9)
    assert ctrl.current_message()["index"] == 1


def test_add_deck_does_not_change_active_when_one_is_already_selected():
    ctrl = Controller()
    ctrl.add_deck(make_deck("a", 2))
    ctrl.add_deck(make_deck("b", 2))
    assert ctrl.active_name == "a"
    assert ctrl.names == ["a", "b"]


def test_follow_replaces_deck_with_same_name_and_keeps_it_active():
    ctrl = Controller()
    ctrl.follow(make_deck("charla", 2), 1)
    ctrl.follow(make_deck("charla", 4), 4)
    msg = ctrl.current_message()
    assert (msg["total"], msg["index"]) == (4, 4)
