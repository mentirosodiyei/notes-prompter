from __future__ import annotations

import pytest

from notes_prompter.protocol import ProtocolError
from notes_prompter.state import Controller


def test_empty_controller_sends_blank_slide():
    ctrl = Controller()
    assert ctrl.current_message() == {
        "type": "slide",
        "presentation": None,
        "index": 0,
        "total": 0,
        "notes": "",
    }


def test_first_loaded_deck_becomes_active(make_pptx):
    ctrl = Controller()
    ctrl.load(str(make_pptx("a", ["uno", "dos"])))
    msg = ctrl.current_message()
    assert (msg["presentation"], msg["index"], msg["total"], msg["notes"]) == ("a", 1, 2, "uno")


def test_next_and_prev_stop_at_edges(make_pptx):
    ctrl = Controller()
    ctrl.load(str(make_pptx("a", ["uno", "dos"])))
    ctrl.prev()
    assert ctrl.current_message()["index"] == 1
    ctrl.next()
    ctrl.next()
    msg = ctrl.current_message()
    assert (msg["index"], msg["notes"]) == (2, "dos")


def test_goto_validates_range(make_pptx):
    ctrl = Controller()
    ctrl.load(str(make_pptx("a", ["uno", "dos", "tres"])))
    ctrl.goto(3)
    assert ctrl.current_message()["notes"] == "tres"
    with pytest.raises(ProtocolError):
        ctrl.goto(0)
    with pytest.raises(ProtocolError):
        ctrl.goto(4)


def test_select_switches_deck_and_resets_index(make_pptx):
    ctrl = Controller()
    ctrl.load(str(make_pptx("a", ["a1", "a2"])))
    ctrl.load(str(make_pptx("b", ["b1", "b2", "b3"])))
    ctrl.goto(2)
    ctrl.select("b")
    msg = ctrl.current_message()
    assert (msg["presentation"], msg["index"], msg["notes"]) == ("b", 1, "b1")
    assert ctrl.names == ["a", "b"]


def test_select_unknown_deck_raises():
    with pytest.raises(ProtocolError):
        Controller().select("nope")


def test_navigation_without_active_deck_raises():
    ctrl = Controller()
    with pytest.raises(ProtocolError):
        ctrl.goto(1)


def test_deck_without_slides_does_not_crash(make_pptx):
    ctrl = Controller()
    ctrl.load(str(make_pptx("vacia", [])))
    assert ctrl.current_message()["total"] == 0
    ctrl.next()
    ctrl.prev()
    assert ctrl.current_message()["notes"] == ""
