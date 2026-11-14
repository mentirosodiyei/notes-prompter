from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from notes_prompter import gui
from notes_prompter.notes import Deck
from notes_prompter.server import create_app
from notes_prompter.settings import SettingsStore
from notes_prompter.state import Controller


def root_for_start(mode):
    return SimpleNamespace(
        _running=False, mode=SimpleNamespace(get=lambda: mode),
        sources={"chosen": gui.LOCAL if mode == "agent" else SimpleNamespace(ip="192.0.2.5", port=8765)},
        source_var=SimpleNamespace(get=lambda: "chosen"),
        _selected_screen=Mock(return_value=object()), _start_agent=Mock(), _start_master=Mock(),
        _open_output=Mock(), _set_running=Mock(), stop_button=Mock(), _say=Mock(), _stop=Mock(),
    )


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_start_agent_never_looks_for_browser_screen_or_opens_output(monkeypatch, platform):
    root = root_for_start("agent")
    root._selected_screen.side_effect = AssertionError("El agente no necesita pantallas")
    monkeypatch.setattr(gui.sys, "platform", platform)
    find = Mock(side_effect=AssertionError("El agente no necesita navegador"))
    monkeypatch.setattr(gui, "find_browser", find)
    gui.App._start(root)
    root._start_agent.assert_called_once_with(None)
    root._open_output.assert_not_called()
    root._start_master.assert_not_called()
    root._set_running.assert_called_once_with(True)
    assert "Enviando" in root._say.call_args.args[0]


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_start_listener_uses_own_master_and_local_output(monkeypatch, platform):
    root = root_for_start("listen")
    monkeypatch.setattr(gui.sys, "platform", platform)
    monkeypatch.setattr(gui, "find_browser", Mock(return_value="test-browser"))
    gui.App._start(root)
    root._start_master.assert_called_once_with("ws://192.0.2.5:8765/ws")
    root._start_agent.assert_not_called()
    assert root._open_output.call_args.args[1] == "http://127.0.0.1:8765/display"
    assert root._open_output.call_args.args[0] == ("native" if platform == "darwin" else "test-browser")


def test_desktop_service_agent_is_announced_but_has_no_settings_or_panel(monkeypatch):
    watcher = SimpleNamespace(poll=lambda: None, close=Mock())
    monkeypatch.setattr(gui, "PowerPointWatcher", Mock(return_value=watcher))
    monkeypatch.setattr(gui, "ServerThread", Mock())
    announce = Mock()
    monkeypatch.setattr(gui, "Announcer", announce)
    root = SimpleNamespace(server=None, _remote_peers=lambda: [], settings_store=SettingsStore())
    gui.App._start_service(root, None, agent=True)
    assert root.admin_app.state.role == "agent"
    announce.assert_called_once()
    root.announcer.start.assert_called_once()
    with TestClient(root.admin_app) as client:
        assert client.get("/api/admin/state").status_code == 403


def test_desktop_service_listener_hosts_own_settings_without_announcing_or_reading_ppt(monkeypatch):
    watcher = Mock(side_effect=AssertionError("El receptor no lee PowerPoint local"))
    monkeypatch.setattr(gui, "PowerPointWatcher", watcher)
    monkeypatch.setattr(gui, "ServerThread", Mock())
    announce = Mock()
    monkeypatch.setattr(gui, "Announcer", announce)
    root = SimpleNamespace(server=None, _remote_peers=lambda: [], settings_store=SettingsStore())
    gui.App._start_service(root, None, agent=False)
    assert root.admin_app.state.role == "master"
    announce.assert_not_called()
    with TestClient(root.admin_app) as client:
        state = client.get("/api/admin/state").json()
        assert state["sources"] == []
        assert state["source_enabled"] is True
        assert client.post("/api/admin/source", json={"source": "local"}).status_code == 409


@pytest.mark.parametrize("path", ["/", "/admin", "/display", "/control", "/static/admin.js", "/api/display-settings", "/api/admin/state"])
def test_agent_rejects_panel_and_configuration_routes(path):
    with TestClient(create_app(role="agent")) as client:
        response = client.get(path)
        assert response.status_code == 403
        assert response.headers["X-Notes-Prompter-Role"] == "agent"
        assert "Escuchar" in response.json()["detail"]


def test_agent_cannot_modify_settings_or_presets_and_exposes_only_notes(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    ctrl = Controller()
    ctrl.add_deck(Deck("Charla", "synthetic.pptx", ("Nota uno", "Nota dos")))
    with TestClient(create_app(ctrl, settings=store, role="agent")) as client:
        for method, path, payload in [("PUT", "/api/admin/live-settings", {}),
                                      ("PUT", "/api/admin/display-settings", {}),
                                      ("POST", "/api/admin/presets", {}),
                                      ("POST", "/api/admin/source", {"source": "local"})]:
            assert client.request(method, path, json=payload).status_code == 403
        assert client.get("/docs").status_code == 404
        assert client.get("/api/agent/state").json()["role"] == "agent"
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "hello", "role": "control"})
            slide = ws.receive_json()
            assert slide["notes"] == "Nota uno"
            assert "display_settings" not in slide
            ws.receive_json()  # presentation catalogue for legacy controls
            ws.send_json({"type": "next"})
            assert ws.receive_json()["type"] == "error"
        assert client.get("/api/agent/state").json()["index"] == 1
    assert not store.path.exists()


def test_receiver_can_prepare_presets_before_any_agent_is_available():
    with TestClient(create_app(peers_fn=lambda: [], allow_local_source=False)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/admin/state").json()["sources"] == []
        assert client.post("/api/admin/presets", json={"name": "Ensayo"}).status_code == 201
