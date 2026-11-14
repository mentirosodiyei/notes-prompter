from io import BytesIO
import json
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from pptx import Presentation

from notes_prompter.notes import Deck, presentation_metadata
from notes_prompter.server import create_app
from notes_prompter.settings import DisplaySettings, PresetInput, SettingsStore
from notes_prompter.state import Controller


def pptx_bytes(total=13):
    deck=Presentation()
    for _ in range(total): deck.slides.add_slide(deck.slide_layouts[6])
    output=BytesIO();deck.save(output)
    return output.getvalue()


def add_bound(store,name,ppt,total,**rules):
    store.remember_presentation(ppt,total)
    preset=store.create_preset(name)
    return store.replace_preset(preset.id,PresetInput(name=name,presentation=ppt,rules={int(k):DisplaySettings(**v) for k,v in rules.items()}))


def test_import_counts_slides_without_loading_notes_and_persists_metadata(tmp_path):
    path=tmp_path/'settings.json'
    with TestClient(create_app(settings=SettingsStore(path))) as client:
        response=client.post('/api/admin/presentations',content=pptx_bytes(13),headers={'X-Presentation-Name':'Cliente%20A.pptx'})
        assert response.status_code==201
        assert response.json()=={'name':'Cliente A','total':13}
        assert client.get('/api/admin/state').json()['slide']['index']==0
    assert SettingsStore(path).document.presentations['cliente a'].total==13


@pytest.mark.parametrize('name,data',[('x.ppt',b'anything'),('x.pptx',b'not a zip')])
def test_invalid_import_leaves_catalog_untouched(name,data):
    with TestClient(create_app()) as client:
        assert client.post('/api/admin/presentations',content=data,headers={'X-Presentation-Name':name}).status_code==422
        assert client.get('/api/admin/state').json()['presentations']==[]


def test_import_rejects_oversized_metadata_and_external_entities():
    for xml in (b'a'*(2*1024*1024+1),b'<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><x/>'):
        output=BytesIO()
        with ZipFile(output,'w') as archive:archive.writestr('ppt/presentation.xml',xml)
        with pytest.raises(ValueError):presentation_metadata(output.getvalue(),'safe.pptx')


def test_automatic_detection_uses_each_ppt_rules_and_remembers_preferred_variant(tmp_path):
    path=tmp_path/'settings.json';store=SettingsStore(path)
    a=add_bound(store,'Cliente A','Charla A',13,**{'2':{'speed_px_s':8}})
    b=add_bound(store,'Cliente B','Charla B',5,**{'3':{'speed_px_s':50}})
    alternate=add_bound(store,'A rápido','Charla A',13,**{'2':{'speed_px_s':70}})
    assert store.effective('CHARLA A.pptx',2).speed_px_s==8
    assert store.effective('Charla B',3).speed_px_s==50
    store.activate(alternate.id)
    restored=SettingsStore(path)
    assert restored.effective('charla a.PPTX',2).speed_px_s==70
    assert restored.effective('Charla B',3).speed_px_s==50
    restored.set_automatic(False)
    assert restored.effective('Charla B',3).speed_px_s==24
    assert restored.context('Charla B',3)['matches'] is False


def test_v2_settings_migrate_without_losing_bound_rules(tmp_path):
    path=tmp_path/'settings.json'
    old={'version':2,'display_settings':{'min_font_px':56},'presets':[{'id':'old','name':'Cliente','presentation':'Charla','defaults':{},'rules':{'2':{'speed_px_s':9}}}], 'active_preset_id':'old'}
    path.write_text(json.dumps(old))
    store=SettingsStore(path)
    assert json.loads(path.with_suffix('.v2-backup.json').read_text()) == old
    assert store.get_preset('old').rules[2].speed_px_s==9
    assert store.effective('Charla',2).speed_px_s==9
    store.remember_presentation('Charla',3)
    restored=SettingsStore(path)
    assert restored.document.version==3 and restored.document.active_preset_id=='old'
    assert restored.value.min_font_px==56


def test_detected_total_limits_new_rules_and_preserves_previous_configuration():
    store=SettingsStore();preset=add_bound(store,'Ensayo','Charla',3)
    before=store.document.model_dump()
    with pytest.raises(ValueError,match='3 diapositivas'):
        store.replace_preset(preset.id,PresetInput(name=preset.name,presentation='Charla',rules={4:DisplaySettings()}))
    assert store.document.model_dump()==before


def test_reduced_slide_count_does_not_erase_previous_rules():
    store=SettingsStore();preset=add_bound(store,'Ensayo','Charla',5,**{'5':{'speed_px_s':10}})
    store.remember_presentation('Charla',3)
    payload=PresetInput(**preset.model_dump(exclude={'id'}))
    payload.rules[2]=DisplaySettings(speed_px_s=40)
    store.replace_preset(preset.id,payload)
    assert 5 in store.get_preset(preset.id).rules
    assert store.effective('Charla',2).speed_px_s==40


def test_current_deck_count_is_detected_and_automatic_preset_is_in_wire_slide():
    ctrl=Controller();ctrl.add_deck(Deck('Charla','file.pptx',tuple('nota' for _ in range(13))))
    store=SettingsStore();preset=add_bound(store,'Ensayo','Charla',13,**{'1':{'speed_px_s':9}})
    with TestClient(create_app(ctrl,settings=store)) as client:
        state=client.get('/api/admin/state').json()
        assert state['presentations']==[{'name':'Charla','total':13}]
        assert state['effective_preset_id']==preset.id and state['active_preset_id'] is None
        with client.websocket_connect('/ws') as ws:
            ws.send_json({'type':'hello','role':'display'})
            assert ws.receive_json()['display_settings']['speed_px_s']==9


def make_live_client(store=None):
    ctrl=Controller();ctrl.add_deck(Deck('Charla','file.pptx',('Nota uno','Nota dos')))
    return ctrl,create_app(ctrl,settings=store)


def scope(index=1,**extra):
    return {'source':'manual','presentation':'Charla','index':index,**extra}


def test_live_font_and_speed_apply_immediately_without_persisting_and_expire_on_slide_change(tmp_path):
    store=SettingsStore(tmp_path/'settings.json');preset=add_bound(store,'Ensayo','Charla',2,**{'1':{'speed_px_s':10},'2':{'speed_px_s':40}})
    before=store.path.read_bytes();ctrl,app=make_live_client(store)
    with TestClient(app) as client:
        with client.websocket_connect('/ws') as ws:
            ws.send_json({'type':'hello','role':'control'});ws.receive_json();ws.receive_json()
            response=client.put('/api/admin/live-settings',json=scope(min_font_px=72,font_mode='fixed',speed_px_s=81))
            assert response.status_code==200
            message=ws.receive_json()
            assert message['live'] and 'restart' not in message
            assert message['font_mode']=='fixed' and message['min_font_px']==72 and message['speed_px_s']==81
            assert store.path.read_bytes()==before
            ws.send_json({'type':'goto','index':2})
            next_slide=ws.receive_json();ws.receive_json()
            assert next_slide['display_settings']['speed_px_s']==40
            assert next_slide['display_settings']['font_mode']=='auto'
            ws.send_json({'type':'goto','index':1})
            assert ws.receive_json()['display_settings']['speed_px_s']==10


def test_live_save_writes_only_current_rule_and_survives_restart(tmp_path):
    store=SettingsStore(tmp_path/'settings.json');preset=add_bound(store,'Ensayo','Charla',2,**{'2':{'speed_px_s':40}})
    ctrl,app=make_live_client(store)
    with TestClient(app) as client:
        assert client.put('/api/admin/live-settings',json=scope(min_font_px=68,font_mode='fixed',speed_px_s=35)).status_code==200
        response=client.post('/api/admin/live-settings/save',json=scope())
        assert response.status_code==200 and not response.json()['live_adjustment']
    restored=SettingsStore(store.path)
    assert restored.effective('Charla',1).speed_px_s==35
    assert restored.effective('Charla',1).font_mode=='fixed'
    assert restored.effective('Charla',2).speed_px_s==40


def test_stale_live_changes_and_save_cannot_touch_the_next_slide():
    store=SettingsStore();add_bound(store,'Ensayo','Charla',2)
    ctrl,app=make_live_client(store)
    with TestClient(app) as client:
        ctrl.goto(2)
        assert client.put('/api/admin/live-settings',json=scope(speed_px_s=70)).status_code==409
        assert client.post('/api/admin/live-settings/save',json=scope()).status_code==409
        assert client.get('/api/display-settings').json()['speed_px_s']==24


def test_live_reset_recovers_the_program_and_no_preset_save_is_rejected():
    ctrl,app=make_live_client()
    with TestClient(app) as client:
        assert client.put('/api/admin/live-settings',json=scope(speed_px_s=70)).status_code==200
        assert client.post('/api/admin/live-settings/save',json=scope()).status_code==409
        response=client.post('/api/admin/live-settings/reset',json=scope())
        assert response.status_code==200
        assert response.json()['effective_display_settings']['speed_px_s']==24
        assert not response.json()['live_adjustment']


def test_new_mutations_reject_foreign_web_origins():
    ctrl,app=make_live_client()
    headers={'Origin':'https://other.example'}
    with TestClient(app) as client:
        assert client.put('/api/admin/live-settings',json=scope(speed_px_s=70),headers=headers).status_code==403
        assert client.put('/api/admin/automatic-preset',json={'enabled':True},headers=headers).status_code==403
        assert client.post('/api/admin/presentations',content=b'x',headers=headers).status_code==403


def test_activating_another_preset_replaces_the_live_override():
    store=SettingsStore();first=add_bound(store,'Normal','Charla',2)
    second=add_bound(store,'Rápido','Charla',2,**{'1':{'speed_px_s':55}})
    ctrl,app=make_live_client(store)
    with TestClient(app) as client:
        client.put('/api/admin/live-settings',json=scope(speed_px_s=80)).raise_for_status()
        response=client.put('/api/admin/active-preset',json={'preset_id':second.id})
        assert response.status_code==200
        assert response.json()['effective_display_settings']['speed_px_s']==55
        assert not response.json()['live_adjustment']


def test_full_auto_font_range_can_be_saved_and_auto_restored_without_losing_speed(tmp_path):
    store = SettingsStore(tmp_path / 'settings.json')
    preset = add_bound(store, 'Ensayo', 'Charla', 2)
    ctrl, app = make_live_client(store)
    with TestClient(app) as client:
        for size in (240, 600):
            result = client.put('/api/admin/live-settings', json=scope(min_font_px=size, font_mode='fixed', speed_px_s=41))
            assert result.status_code == 200
            assert result.json()['effective_display_settings']['min_font_px'] == size
        for invalid in (601, 23, True):
            assert client.put('/api/admin/live-settings', json=scope(min_font_px=invalid)).status_code == 422
        assert client.post('/api/admin/live-settings/save', json=scope()).status_code == 200
        assert SettingsStore(store.path).get_preset(preset.id).rules[1].min_font_px == 600
        state = client.put('/api/admin/live-settings', json=scope(font_mode='auto', min_font_px=48)).json()
        assert state['effective_display_settings']['font_mode'] == 'auto'
        assert state['effective_display_settings']['speed_px_s'] == 41
        assert state['programmed_display_settings']['min_font_px'] == 600
        assert client.post('/api/admin/live-settings/save', json=scope()).status_code == 200
        restored = SettingsStore(store.path).get_preset(preset.id).rules[1]
        assert restored.font_mode == 'auto' and restored.min_font_px == 48


@pytest.mark.parametrize('speed', [-200, -12.5, 0, 200])
def test_signed_live_speed_broadcasts_saves_and_survives_restart(tmp_path, speed):
    store = SettingsStore(tmp_path / 'signed.json')
    preset = add_bound(store, 'Reversible', 'Charla', 2)
    ctrl, app = make_live_client(store)
    with TestClient(app) as client, client.websocket_connect('/ws') as ws:
        ws.send_json({'type':'hello','role':'display'})
        ws.receive_json()
        result = client.put('/api/admin/live-settings', json=scope(speed_px_s=speed))
        assert result.status_code == 200
        assert ws.receive_json()['speed_px_s'] == speed
        assert result.json()['speed_limits'] == {'min':-200,'max':200}
        assert client.post('/api/admin/live-settings/save', json=scope()).status_code == 200
        assert SettingsStore(store.path).get_preset(preset.id).rules[1].speed_px_s == speed
        assert store.effective('Charla', 2).speed_px_s == 24
        assert client.put('/api/admin/live-settings', json=scope(index=2, speed_px_s=speed)).status_code == 409


@pytest.mark.parametrize('speed', [-201, 201, True, '0', float('inf')])
def test_signed_speed_rejects_invalid_values_without_changing_settings(speed):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DisplaySettings(speed_px_s=speed)
