from __future__ import annotations

from fastapi.testclient import TestClient

from notes_prompter.notes import Deck
from notes_prompter.powerpoint import SlideState
from notes_prompter.server import create_app


class FakeWatcher:
    """Devuelve siempre la misma diapositiva: la del seguimiento de PowerPoint."""

    def __init__(self, deck: Deck, index: int) -> None:
        self._state = SlideState(deck=deck, index=index)

    def poll(self) -> SlideState:
        return self._state


def test_powerpoint_slide_is_served_to_displays():
    deck = Deck(name="charla", path="C:\\charla.pptx", notes=("uno", "dos", "tres"))
    app = create_app(powerpoint=FakeWatcher(deck, 2), poll_interval=0.01)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "hello", "role": "display"})
            slide = ws.receive_json()
            assert (slide["presentation"], slide["index"], slide["total"], slide["notes"]) == (
                "charla",
                2,
                3,
                "dos",
            )
