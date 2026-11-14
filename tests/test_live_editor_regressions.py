"""Explicit preset edits must replace the temporary reading they supersede."""
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from notes_prompter.notes import Deck
from notes_prompter.server import create_app
from notes_prompter.settings import SettingsStore, PresetInput, DisplaySettings
from notes_prompter.state import Controller


def fixture():
    store = SettingsStore()
    preset = store.create_preset("Ensayo")
    store.replace_preset(preset.id, PresetInput(name=preset.name, presentation="Charla"))
    ctrl = Controller()
    ctrl.add_deck(Deck("Charla", "synthetic.pptx", ("Nota uno", "Nota dos")))
    return store, preset, create_app(ctrl, settings=store)


def live_scope(**values):
    return {"source": "manual", "presentation": "Charla", "index": 1, **values}


def test_saving_current_active_rule_replaces_live_override_and_broadcasts():
    store, preset, app = fixture()
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "hello", "role": "display"})
        ws.receive_json()
        assert client.put("/api/admin/live-settings", json=live_scope(speed_px_s=50, min_font_px=80, font_mode="fixed")).status_code == 200
        ws.receive_json()
        payload = store.get_preset(preset.id).model_dump(mode="json", exclude={"id"})
        payload["rules"]["1"] = DisplaySettings(speed_px_s=12, min_font_px=64, font_mode="fixed").model_dump()
        assert client.put(f"/api/admin/presets/{preset.id}", json=payload).status_code == 200
        message = ws.receive_json()
        assert message["speed_px_s"] == 12 and message["min_font_px"] == 64
        assert message["restart"] is True
        state = client.get("/api/admin/state").json()
        assert state["live_adjustment"] is False
        assert state["effective_display_settings"]["speed_px_s"] == 12
        assert state["presets"][0]["rules"]["1"]["speed_px_s"] == 12


def test_editing_future_rule_preserves_current_live_reading():
    store, preset, app = fixture()
    with TestClient(app) as client:
        client.put("/api/admin/live-settings", json=live_scope(speed_px_s=50))
        payload = store.get_preset(preset.id).model_dump(mode="json", exclude={"id"})
        payload["rules"]["2"] = DisplaySettings(speed_px_s=12).model_dump()
        assert client.put(f"/api/admin/presets/{preset.id}", json=payload).status_code == 200
        state = client.get("/api/admin/state").json()
        assert state["live_adjustment"] is True
        assert state["effective_display_settings"]["speed_px_s"] == 50


def test_editing_an_inactive_variant_preserves_current_live_reading():
    store, preset, app = fixture()
    copy = store.create_preset("Otra versión", copy_from=preset.id)
    with TestClient(app) as client:
        client.put("/api/admin/live-settings", json=live_scope(speed_px_s=50))
        payload = copy.model_dump(mode="json", exclude={"id"})
        payload["rules"]["1"] = DisplaySettings(speed_px_s=12).model_dump()
        assert client.put(f"/api/admin/presets/{copy.id}", json=payload).status_code == 200
        state = client.get("/api/admin/state").json()
        assert state["effective_preset_id"] == preset.id
        assert state["live_adjustment"] is True
        assert state["effective_display_settings"]["speed_px_s"] == 50


def test_failed_preset_save_preserves_programming_and_live_override(monkeypatch):
    store, preset, app = fixture()
    with TestClient(app) as client:
        client.put("/api/admin/live-settings", json=live_scope(speed_px_s=50))
        payload = store.get_preset(preset.id).model_dump(mode="json", exclude={"id"})
        payload["rules"]["1"] = DisplaySettings(speed_px_s=12).model_dump()
        monkeypatch.setattr(store, "_commit", Mock(side_effect=OSError("disco no disponible")))
        assert client.put(f"/api/admin/presets/{preset.id}", json=payload).status_code == 503
        state = client.get("/api/admin/state").json()
        assert state["live_adjustment"] is True
        assert state["effective_display_settings"]["speed_px_s"] == 50
        assert state["presets"][0]["rules"] == {}


def test_removing_active_preset_clears_temporary_adjustments():
    _, preset, app = fixture()
    with TestClient(app) as client:
        client.put("/api/admin/live-settings", json=live_scope(speed_px_s=50))
        assert client.delete(f"/api/admin/presets/{preset.id}").status_code == 200
        state = client.get("/api/admin/state").json()
        assert state["live_adjustment"] is False
        assert state["effective_display_settings"]["speed_px_s"] == 24


def test_saving_general_reading_replaces_its_live_override():
    ctrl = Controller()
    ctrl.add_deck(Deck("Charla", "synthetic.pptx", ("Nota",)))
    with TestClient(create_app(ctrl)) as client:
        client.put("/api/admin/live-settings", json=live_scope(speed_px_s=50))
        assert client.put("/api/admin/display-settings", json=DisplaySettings(speed_px_s=12).model_dump()).status_code == 200
        state = client.get("/api/admin/state").json()
        assert state["live_adjustment"] is False
        assert state["effective_display_settings"]["speed_px_s"] == 12


def test_direct_live_access_targets_the_receiver_master_in_listen_mode(monkeypatch):
    from notes_prompter import gui
    opened = Mock()
    monkeypatch.setattr(gui.webbrowser, "open", opened)
    root = SimpleNamespace(mode=SimpleNamespace(get=lambda: "listen"),
        sources={"pc": SimpleNamespace(ip="192.0.2.10", port=8765)},
        source_var=SimpleNamespace(get=lambda: "pc"), server=object())
    gui.App._open_admin(root, section="live-controls")
    assert opened.call_args.args[0] == f"http://127.0.0.1:8765/?v={gui.__version__}#live-controls"


def test_agent_does_not_open_live_panel(monkeypatch):
    from notes_prompter import gui
    opened = Mock()
    monkeypatch.setattr(gui.webbrowser, "open", opened)
    root = SimpleNamespace(mode=SimpleNamespace(get=lambda: "agent"),
        sources={}, source_var=SimpleNamespace(get=lambda: "local"), server=object(), _say=Mock())
    gui.App._open_admin(root, section="live-controls")
    opened.assert_not_called()
    assert "receptor" in root._say.call_args.args[0]
