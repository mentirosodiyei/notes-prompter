from __future__ import annotations

import json
import socket
import threading

import pytest
import uvicorn
from fastapi.testclient import TestClient
from websockets.sync.client import connect

from notes_prompter.server import create_app
from notes_prompter.state import Controller

RECV_TIMEOUT = 5


@pytest.fixture
def client():
    return TestClient(create_app(Controller()))


@pytest.fixture
def live_url():
    """Servidor uvicorn real en un hilo. Varios clientes WebSocket a la vez
    necesitan un único bucle de eventos, como en producción; TestClient no lo da."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(Controller()), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        pass
    yield f"ws://127.0.0.1:{port}/ws"
    server.should_exit = True
    thread.join(timeout=5)


def recv(ws) -> dict:
    return json.loads(ws.recv(timeout=RECV_TIMEOUT))


def send(ws, payload: dict) -> None:
    ws.send(json.dumps(payload))


def test_pages_are_served(client):
    assert client.get("/").status_code == 200
    assert "Presets de ensayo" in client.get("/").text
    assert "Notas en directo" in client.get("/").text
    assert client.get("/").text == client.get("/admin").text
    assert client.get("/control").status_code == 200
    assert "goto-form" in client.get("/control").text
    assert client.get("/display").status_code == 200
    assert "receptor" in client.get("/display").text
    assert client.get("/static/display.js").status_code == 200


def test_display_gets_blank_slide_on_hello(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "hello", "role": "display"})
        message = ws.receive_json()
        from notes_prompter.settings import DisplaySettings
        assert message.pop("display_settings") == DisplaySettings().model_dump()
        assert message.pop("playback") == {"source":"manual","presentation":None,"index":0,"paused":False,"restart_id":0,"revision":0}
        assert message == {
            "type": "slide",
            "presentation": None,
            "index": 0,
            "total": 0,
            "notes": "",
        }


def test_control_loads_and_navigates_and_display_follows(live_url, make_pptx):
    path = str(make_pptx("charla", ["uno", "dos", "tres"]))

    with connect(live_url) as display, connect(live_url) as control:
        send(display, {"type": "hello", "role": "display"})
        recv(display)
        send(control, {"type": "hello", "role": "control"})
        recv(control)  # slide
        recv(control)  # presentations

        send(control, {"type": "load", "path": path})
        for ws in (display, control):
            slide = recv(ws)
            assert (slide["type"], slide["presentation"], slide["index"], slide["total"], slide["notes"]) == (
                "slide",
                "charla",
                1,
                3,
                "uno",
            )
        assert recv(control) == {"type": "presentations", "items": ["charla"], "active": "charla"}

        send(control, {"type": "next"})
        assert recv(display)["notes"] == "dos"
        assert recv(control)["index"] == 2
        recv(control)  # presentations

        send(control, {"type": "goto", "index": 3})
        assert recv(display)["notes"] == "tres"
        recv(control)
        recv(control)

        send(control, {"type": "goto", "index": 99})
        assert recv(control) == {
            "type": "error",
            "message": "índice fuera de rango: 99 (1..3)",
        }


def test_display_cannot_send_commands(live_url):
    with connect(live_url) as ws:
        send(ws, {"type": "hello", "role": "display"})
        recv(ws)
        send(ws, {"type": "next"})
        assert recv(ws)["type"] == "error"


def test_command_before_hello_is_rejected(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "next"})
        assert ws.receive_json()["type"] == "error"


def test_invalid_json_returns_error_and_keeps_connection(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text("{roto")
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "hello", "role": "display"})
        assert ws.receive_json()["type"] == "slide"


def test_loading_a_bad_file_reports_error(client, tmp_path):
    bad = tmp_path / "falso.pptx"
    bad.write_bytes(b"no soy un zip")
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "hello", "role": "control"})
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "load", "path": str(bad)})
        assert ws.receive_json()["type"] == "error"
