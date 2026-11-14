from fastapi.testclient import TestClient
import pytest
from notes_prompter.notes import Deck
from notes_prompter.state import Controller
from notes_prompter.server import create_app
from notes_prompter.settings import SettingsStore, DisplaySettings


def fixture(store=None, **kwargs):
    ctrl=Controller();ctrl.add_deck(Deck('Ensayo','ensayo.pptx',('Nota larga','Otra nota')))
    return ctrl,create_app(ctrl,settings=store,**kwargs)


def scope(**extra):
    return {'source':'manual','presentation':'Ensayo','index':1,**extra}


def test_panel_pause_resume_restart_reaches_two_displays_and_late_connection(tmp_path):
    store=SettingsStore(tmp_path/'settings.json');store.update(DisplaySettings(speed_px_s=-30))
    ctrl,app=fixture(store)
    with TestClient(app) as client, client.websocket_connect('/ws') as first, client.websocket_connect('/ws') as second:
        before=store.path.read_bytes()
        for ws in (first,second):
            ws.send_json({'type':'hello','role':'display'});assert not ws.receive_json()['playback']['paused']
        state=client.post('/api/admin/playback',json=scope(action='pause')).json()
        assert state['playback']['paused'] is True
        for ws in (first,second):assert ws.receive_json()['paused'] is True
        with client.websocket_connect('/ws') as late:
            late.send_json({'type':'hello','role':'display'});assert late.receive_json()['playback']['paused'] is True
        state=client.post('/api/admin/playback',json=scope(action='restart')).json()
        assert state['playback']['paused'] is True and state['playback']['restart_id']==1
        for ws in (first,second):assert ws.receive_json()['restart_id']==1
        state=client.post('/api/admin/playback',json=scope(action='resume')).json()
        assert not state['playback']['paused']
        for ws in (first,second):assert not ws.receive_json()['paused']
        assert state['effective_display_settings']['speed_px_s']==-30
    assert store.path.read_bytes()==before


def test_pause_survives_live_and_program_changes_and_resets_with_slide():
    ctrl,app=fixture()
    with TestClient(app) as client:
        client.post('/api/admin/playback',json=scope(action='pause')).raise_for_status()
        state=client.put('/api/admin/live-settings',json=scope(speed_px_s=0,min_font_px=60)).json()
        assert state['playback']['paused']
        client.put('/api/admin/display-settings',json={'speed_px_s':-20}).raise_for_status()
        assert client.get('/api/admin/state').json()['playback']['paused']
        ctrl.goto(2)
        assert not client.get('/api/admin/state').json()['playback']['paused']
        assert client.post('/api/admin/playback',json=scope(action='restart')).status_code==409
        ctrl.goto(1)
        assert not client.get('/api/admin/state').json()['playback']['paused']


@pytest.mark.parametrize('payload,code', [
    (scope(action='unknown'),422), (scope(action='pause',index=2),409),
    (scope(action='restart',source='other'),409), (scope(action='resume',presentation='other'),409)])
def test_playback_rejects_invalid_or_stale_commands(payload,code):
    _,app=fixture()
    with TestClient(app) as client:
        assert client.post('/api/admin/playback',json=payload).status_code==code
        assert not client.get('/api/admin/state').json()['playback']['paused']
        assert client.get('/api/admin/state').json()['playback']['restart_id']==0


def test_playback_origin_and_agent_role_are_rejected():
    _,app=fixture()
    with TestClient(app) as client:
        assert client.post('/api/admin/playback',json=scope(action='pause'),headers={'Origin':'https://other.example'}).status_code==403
    _,app=fixture(role='agent')
    with TestClient(app) as client:
        assert client.post('/api/admin/playback',json=scope(action='pause')).status_code==403


def test_controls_are_only_in_panel_and_mark_zero_in_both_sliders():
    _,app=fixture()
    with TestClient(app) as client:
        panel=client.get('/admin').text;display=client.get('/display').text
        for identifier in ('pause-scroll','restart-scroll'):
            assert f'id="{identifier}"' in panel
            assert identifier not in display
        assert panel.count('class="speed-zero"')==2
        assert 'value="0" label="0"' in panel


def test_playback_revisions_are_monotonic_and_refresh_does_not_increment():
    _,app=fixture()
    with TestClient(app) as client:
        assert client.get('/api/admin/state').json()['playback']['revision']==0
        for revision,action in enumerate(('pause','restart','resume','pause'),1):
            state=client.post('/api/admin/playback',json=scope(action=action)).json()
            assert state['playback']['revision']==revision
            assert client.get('/api/admin/state').json()['playback']['revision']==revision
