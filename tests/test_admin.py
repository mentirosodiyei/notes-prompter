from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from notes_prompter import __version__
from notes_prompter.discovery import Peer
from notes_prompter.server import create_app
from notes_prompter.settings import DisplaySettings, SettingsStore


def test_admin_and_settings_are_served():
    with TestClient(create_app()) as client:
        assert client.get('/admin').status_code == 200
        for name in ['admin.css', 'admin.js']:
            assert client.get('/static/'+name).status_code == 200
        data = client.get('/api/admin/state').json()
        assert data['source_enabled'] is False
        assert data['display_settings']['min_font_px'] == 48
        assert client.get('/api/display-settings').json()['auto_scroll'] is True


def test_settings_broadcast_and_persist(tmp_path):
    path = tmp_path / 'config' / 'settings.json'
    values = dict(auto_scroll=True, font_mode='auto', min_font_px=56, speed_px_s=32, start_delay_s=1.5)
    with TestClient(create_app(settings=SettingsStore(path))) as client:
        with client.websocket_connect('/ws') as ws:
            ws.send_json(dict(type='hello', role='display'))
            assert ws.receive_json()['type'] == 'slide'
            assert client.put('/api/admin/display-settings', json=values).json() == values
            message=ws.receive_json()
            assert message.pop('playback')['paused'] is False
            assert message == dict(type='display_settings', **values)
        assert client.get('/api/display-settings').json() == values
    assert SettingsStore(path).value.model_dump() == values
    assert not path.with_suffix('.tmp').exists()


@pytest.mark.parametrize('field,value', [
    ('min_font_px', 8), ('min_font_px', True), ('speed_px_s', -201), ('speed_px_s', 201),
    ('speed_px_s', True), ('start_delay_s', -1), ('start_delay_s', 31), ('auto_scroll', 'true'),
])
def test_invalid_reading_settings_leave_current_values(field, value):
    values = DisplaySettings().model_dump()
    changed = dict(values, **{field:value})
    with TestClient(create_app()) as client:
        assert client.put('/api/admin/display-settings', json=changed).status_code == 422
        assert client.get('/api/display-settings').json() == values


def test_failed_settings_save_does_not_apply_change(monkeypatch):
    store = SettingsStore()
    def fail(_):
        raise OSError('disco no disponible')
    monkeypatch.setattr(store, 'update', fail)
    with TestClient(create_app(settings=store)) as client:
        assert client.put('/api/admin/display-settings', json=dict(auto_scroll=False)).status_code == 503
        assert client.get('/api/display-settings').json()['auto_scroll'] is True


def test_cross_origin_changes_are_rejected():
    with TestClient(create_app()) as client:
        assert client.put('/api/admin/display-settings', json={}, headers={'Origin':'https://otra-web.example'}).status_code == 403
        assert client.put('/api/admin/display-settings', json={}, headers={'Origin':'http://testserver'}).status_code == 200


def test_manual_control_cannot_switch_sources():
    with TestClient(create_app()) as client:
        assert client.post('/api/admin/source', json={'source':'local'}).status_code == 409


def test_expired_peer_does_not_replace_the_current_source():
    with TestClient(create_app(peers_fn=lambda: [])) as client:
        assert client.post('/api/admin/source', json={'source':'10.0.0.2:8765'}).status_code == 409
        assert client.get('/api/admin/state').json()['source'] == 'manual'


def test_corrupt_settings_file_falls_back_to_defaults(tmp_path):
    path=tmp_path/'settings.json'
    path.write_text('{roto', encoding='utf-8')
    assert SettingsStore(path).value == DisplaySettings()


def test_master_root_has_live_notes_and_all_preset_controls():
    from notes_prompter.notes import Deck
    from notes_prompter.state import Controller
    ctrl=Controller()
    ctrl.add_deck(Deck('charla','charla.pptx',('Notas del master visibles en el panel',)))
    with TestClient(create_app(ctrl)) as client:
        root=client.get('/')
        assert root.status_code==200
        for element in ['id="live-notes"','id="preview-notes"','id="presets"','id="preset-select"','id="rules-table"']:
            assert element in root.text
        data=client.get('/api/admin/state').json()
        assert data['slide']['notes']=='Notas del master visibles en el panel'
        assert data['version']==__version__
        assert {'master_dashboard','presets','slide_rules'} <= set(data['features'])
        assert client.get('/admin').text==root.text
        assert 'Control manual' in client.get('/control').text or 'control manual' in client.get('/control').text


@pytest.mark.parametrize('path',['/','/admin','/control','/display','/static/admin.js','/api/admin/state'])
def test_master_pages_and_assets_are_not_reused_from_an_older_cache(path):
    with TestClient(create_app()) as client:
        response=client.get(path)
        assert response.status_code==200
        assert 'no-store' in response.headers['cache-control']
        assert response.headers['x-notes-prompter-version']==__version__
