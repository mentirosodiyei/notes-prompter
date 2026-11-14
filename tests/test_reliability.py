from __future__ import annotations

import json
import socket
import threading
import time
from contextlib import contextmanager, ExitStack

import pytest
import uvicorn
from websockets.sync.client import connect

from notes_prompter.discovery import Announcer, PeerListener
from notes_prompter.notes import Deck
from notes_prompter.powerpoint import SlideState
from notes_prompter.protocol import ProtocolError, parse_slide
from notes_prompter.server import create_app
from notes_prompter.state import Controller


@contextmanager
def running_server(app, port=0):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started:
                assert thread.is_alive() and time.monotonic() < deadline
                time.sleep(0.01)
            yield port
        finally:
            server.should_exit = True
            thread.join(5)
            assert not thread.is_alive()


def receive_slide(ws, index):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        message = json.loads(ws.recv(timeout=max(0.01, deadline - time.monotonic())))
        if message.get("type") == "slide" and message["index"] == index:
            return message
    pytest.fail("No llegó la diapositiva esperada")


def test_remote_agent_relays_changes_and_clears_on_disconnect():
    ctrl = Controller()
    ctrl.add_deck(Deck(name="origen", path="origen.pptx", notes=("uno", "dos")))
    with ExitStack() as origin_stack:
        origin_port = origin_stack.enter_context(running_server(create_app(ctrl)))
        relay = create_app(upstream=f"ws://127.0.0.1:{origin_port}/ws", reconnect_interval=0.01)
        with running_server(relay) as relay_port:
            with connect(f"ws://127.0.0.1:{relay_port}/ws") as display:
                display.send(json.dumps({"type": "hello", "role": "display"}))
                assert receive_slide(display, 1)["notes"] == "uno"
                with connect(f"ws://127.0.0.1:{origin_port}/ws") as control:
                    control.send(json.dumps({"type": "hello", "role": "control"}))
                    control.recv(timeout=3)
                    control.recv(timeout=3)
                    control.send(json.dumps({"type": "goto", "index": 2}))
                    assert receive_slide(display, 2)["notes"] == "dos"
                assert relay.state.presentation_name() == "origen"
                origin_stack.close()
                assert receive_slide(display, 0)["presentation"] is None
                assert relay.state.presentation_name() is None


def test_watcher_recovers_after_exception_and_disappearance():
    class Watcher:
        state = SlideState(Deck("charla", "charla.pptx", ("nota",)), 1)
        closed = False

        def poll(self):
            if isinstance(self.state, Exception):
                raise self.state
            return self.state

        def close(self):
            self.closed = True

    watcher = Watcher()
    with running_server(create_app(powerpoint=watcher, poll_interval=0.01)) as port:
        with connect(f"ws://127.0.0.1:{port}/ws") as display:
            display.send(json.dumps({"type": "hello", "role": "display"}))
            assert receive_slide(display, 1)["notes"] == "nota"
            watcher.state = RuntimeError("PowerPoint ocupado")
            assert receive_slide(display, 0)["notes"] == ""
            watcher.state = SlideState(Deck("charla", "charla.pptx", ("nota nueva",)), 1)
            assert receive_slide(display, 1)["notes"] == "nota nueva"
    assert watcher.closed


@pytest.mark.parametrize("message", [
    [], {"type": "slide", "presentation": "x", "index": True, "total": 1, "notes": "x"},
    {"type": "slide", "presentation": "x", "index": 2, "total": 1, "notes": "x"},
    {"type": "slide", "presentation": None, "index": 1, "total": 1, "notes": "x"},
    {"type": "slide", "presentation": None, "index": 0, "total": 0, "notes": "x"},
])
def test_remote_slide_rejects_invalid_payload(message):
    with pytest.raises(ProtocolError):
        parse_slide(json.dumps(message))


def test_discovery_threads_can_stop_and_join():
    listener = PeerListener(discovery_port=0)
    announcer = Announcer("prueba", 8765, lambda: "", discovery_port=9, interval=0.01)
    listener.start()
    announcer.start()
    listener.stop()
    announcer.stop()
    listener.join(2)
    announcer.join(2)
    assert not listener.is_alive() and not announcer.is_alive()


def test_remote_agent_reconnects_when_origin_appears_and_restarts():
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        origin_port = reserve.getsockname()[1]
    relay = create_app(upstream=f"ws://127.0.0.1:{origin_port}/ws", reconnect_interval=0.02)
    with running_server(relay) as relay_port:
        with connect(f"ws://127.0.0.1:{relay_port}/ws") as display:
            display.send(json.dumps({"type": "hello", "role": "display"}))
            assert receive_slide(display, 0)["notes"] == ""
            ctrl = Controller()
            ctrl.add_deck(Deck("charla", "charla.pptx", ("antes",)))
            with running_server(create_app(ctrl), origin_port):
                assert receive_slide(display, 1)["notes"] == "antes"
            assert receive_slide(display, 0)["presentation"] is None
            ctrl = Controller()
            ctrl.add_deck(Deck("charla", "charla.pptx", ("después",)))
            with running_server(create_app(ctrl), origin_port):
                assert receive_slide(display, 1)["notes"] == "después"


def test_admin_can_switch_local_remote_local_without_restarting_server(monkeypatch):
    import httpx
    from notes_prompter.discovery import Peer
    from notes_prompter import server as server_module

    class Watcher:
        def __init__(self, note):
            self.closed = False
            self.note = note
        def poll(self):
            return SlideState(Deck('local', 'local.pptx', (self.note,)), 1)
        def close(self):
            self.closed = True

    initial = Watcher('local inicial')
    replacement = Watcher('local recuperado')
    monkeypatch.setattr(server_module, 'PowerPointWatcher', lambda: replacement)
    origin = Controller()
    origin.add_deck(Deck('remota','remota.pptx',('nota de otro PC',)))
    with running_server(create_app(origin)) as origin_port:
        peer = Peer('127.0.0.1', origin_port, 'PC-ORIGEN', 'remota')
        app=create_app(powerpoint=initial, peers_fn=lambda:[peer], poll_interval=0.01)
        with running_server(app) as port:
            base=f'http://127.0.0.1:{port}'
            with connect(f'ws://127.0.0.1:{port}/ws') as display:
                display.send(json.dumps({'type':'hello','role':'display'}))
                assert receive_slide(display,1)['notes']=='local inicial'
                response=httpx.post(base+'/api/admin/source',json={'source':f'127.0.0.1:{origin_port}'})
                assert response.status_code==200
                assert receive_slide(display,1)['notes']=='nota de otro PC'
                assert initial.closed
                assert httpx.post(base+'/api/admin/source',json={'source':'local'}).status_code==200
                assert receive_slide(display,1)['notes']=='local recuperado'
        assert replacement.closed


def test_editing_a_future_rule_does_not_restart_current_display():
    import httpx
    from websockets.sync.client import connect
    from notes_prompter.settings import SettingsStore, PresetInput, DisplaySettings
    store=SettingsStore()
    preset=store.create_preset('Ensayo en directo')
    store.activate(preset.id)
    ctrl=Controller(); ctrl.add_deck(Deck('charla','charla.pptx',('nota uno','nota dos')))
    with running_server(create_app(ctrl,settings=store)) as port:
        with connect(f'ws://127.0.0.1:{port}/ws') as display:
            display.send(json.dumps({'type':'hello','role':'display'}))
            assert receive_slide(display,1)['display_settings']['speed_px_s']==24
            payload=PresetInput(name=preset.name,rules={2:DisplaySettings(speed_px_s=11)}).model_dump(mode='json')
            assert httpx.put(f'http://127.0.0.1:{port}/api/admin/presets/{preset.id}',json=payload).status_code==200
            with pytest.raises(TimeoutError):
                display.recv(timeout=.15)


def test_receiver_owns_presets_live_settings_and_selection_between_notes_only_agents(tmp_path):
    import httpx
    from notes_prompter.discovery import Peer
    from notes_prompter.settings import SettingsStore, DisplaySettings, PresetInput

    class Watcher:
        def __init__(self, name):
            self.deck = Deck(name, "synthetic.pptx", ("Nota uno", "Nota dos", "Nota tres"))
            self.index = 1
        def poll(self):
            return SlideState(self.deck, self.index)
        def close(self):
            pass

    a, b = Watcher("PPT A"), Watcher("PPT B")
    agent_store = SettingsStore(tmp_path / "agent.json")
    agent_store.update(DisplaySettings(speed_px_s=111))
    original_agent_settings = agent_store.path.read_bytes()
    receiver_store = SettingsStore(tmp_path / "receiver.json")
    preset = receiver_store.create_preset("Ensayo A")
    receiver_store.replace_preset(preset.id, PresetInput(name=preset.name, presentation="PPT A",
        rules={2: DisplaySettings(min_font_px=72, font_mode="fixed", speed_px_s=10)}))
    with running_server(create_app(powerpoint=a, role="agent", settings=agent_store, poll_interval=.01)) as port_a:
        with running_server(create_app(powerpoint=b, role="agent", poll_interval=.01)) as port_b:
            peers = [Peer("127.0.0.1", port_a, "PC A", "PPT A"), Peer("127.0.0.1", port_b, "PC B", "PPT B")]
            source_a = f"127.0.0.1:{port_a}"
            source_b = f"127.0.0.1:{port_b}"
            app = create_app(upstream=f"ws://{source_a}/ws", peers_fn=lambda: peers,
                             allow_local_source=False, settings=receiver_store)
            with running_server(app) as receiver_port:
                base = f"http://127.0.0.1:{receiver_port}"
                assert httpx.get(f"http://{source_a}/api/admin/state").status_code == 403
                with connect(f"ws://{source_a}/ws") as origin:
                    origin.send(json.dumps({"type": "hello", "role": "display"}))
                    assert "display_settings" not in receive_slide(origin, 1)
                with connect(f"ws://127.0.0.1:{receiver_port}/ws") as display:
                    display.send(json.dumps({"type": "hello", "role": "display"}))
                    first = receive_slide(display, 1)
                    assert first["presentation"] == "PPT A"
                    assert first["display_settings"]["speed_px_s"] == 24
                    state = httpx.get(base + "/api/admin/state").json()
                    assert state["role"] == "master"
                    assert [s["id"] for s in state["sources"]] == [source_a, source_b]
                    scope = {"source": source_a, "presentation": "PPT A", "index": 1}
                    assert httpx.put(base + "/api/admin/live-settings", json={**scope, "min_font_px": 80,
                        "font_mode": "fixed", "speed_px_s": 50}).status_code == 200
                    assert json.loads(display.recv(timeout=3))["speed_px_s"] == 50
                    assert httpx.post(base + "/api/admin/live-settings/save", json=scope).status_code == 200
                    assert json.loads(display.recv(timeout=3))["min_font_px"] == 80
                    a.index = 2
                    second = receive_slide(display, 2)
                    assert second["display_settings"]["speed_px_s"] == 10
                    assert second["display_settings"]["min_font_px"] == 72
                    a.index = 1
                    assert receive_slide(display, 1)["display_settings"]["speed_px_s"] == 50
                    assert httpx.post(base + "/api/admin/source", json={"source": source_b}).status_code == 200
                    other = receive_slide(display, 1)
                    assert other["presentation"] == "PPT B"
                    assert other["display_settings"]["speed_px_s"] == 24
                    assert httpx.post(base + "/api/admin/source", json={"source": "local"}).status_code == 409
    assert agent_store.path.read_bytes() == original_agent_settings
    saved = SettingsStore(receiver_store.path).get_preset(preset.id)
    assert saved.rules[1].speed_px_s == 50 and saved.rules[1].min_font_px == 80


def test_unsaved_com_notes_reach_receiver_without_changing_slide_or_restarting():
    from test_powerpoint import fake_app, fake_presentation
    from notes_prompter.powerpoint import PowerPointWatcher
    pres = fake_presentation("Charla viva", ["Nota original", "Segunda"])
    watcher = PowerPointWatcher(fake_app(pres))
    agent = create_app(powerpoint=watcher, role="agent", poll_interval=0.01)
    with running_server(agent) as agent_port:
        receiver = create_app(upstream=f"ws://127.0.0.1:{agent_port}/ws", allow_local_source=False)
        with running_server(receiver) as port, connect(f"ws://127.0.0.1:{port}/ws") as display:
            display.send(json.dumps({"type": "hello", "role": "display"}))
            assert receive_slide(display, 1)["notes"] == "Nota original"
            for text in ("Cambio sin guardar", "Otra edición", ""):
                pres.Slides(1).NotesPage.Shapes.Placeholders(1).TextFrame.TextRange.Text = text
                message = receive_slide(display, 1)
                assert message["notes"] == text
                assert message["total"] == 2
                assert message["display_settings"]["font_mode"] == "auto"
