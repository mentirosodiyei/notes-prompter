import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from notes_prompter.notes import Deck
from notes_prompter.server import create_app
from notes_prompter.settings import DisplaySettings, PresetInput, SettingsStore
from notes_prompter.state import Controller


def test_legacy_preferences_migrate_and_active_preset_survives_restart(tmp_path):
    path=tmp_path/'settings.json'
    legacy=DisplaySettings(speed_px_s=31).model_dump()
    path.write_text(json.dumps(legacy),encoding='utf-8')
    store=SettingsStore(path)
    preset=store.create_preset('Cliente A')
    payload=PresetInput(name='Cliente A',presentation='charla',defaults=store.value,
                        rules={2:DisplaySettings(auto_scroll=False),5:DisplaySettings(speed_px_s=18,start_delay_s=4)})
    store.replace_preset(preset.id,payload)
    store.activate(preset.id)
    restored=SettingsStore(path)
    assert restored.value.model_dump()==legacy
    assert restored.document.active_preset_id==preset.id
    assert restored.effective('charla',5).speed_px_s==18
    assert restored.effective('charla',5).start_delay_s==4
    assert restored.effective('charla',2).auto_scroll is False
    assert restored.effective('charla',3).speed_px_s==31
    assert restored.effective('otra charla',5).speed_px_s==31
    assert json.loads(path.read_text())['version']==3


def test_duplicate_preset_has_independent_rules_and_unique_name():
    store=SettingsStore()
    original=store.create_preset('Ensayo')
    store.replace_preset(original.id,PresetInput(name='Ensayo',rules={1:DisplaySettings(speed_px_s=10)}))
    copy=store.create_preset(copy_from=original.id)
    another=store.create_preset(copy_from=original.id)
    assert copy.id!=original.id and another.name!=copy.name
    store.replace_preset(copy.id,PresetInput(name=copy.name,rules={1:DisplaySettings(speed_px_s=45)}))
    assert store.get_preset(original.id).rules[1].speed_px_s==10
    assert store.get_preset(copy.id).rules[1].speed_px_s==45
    with pytest.raises(ValueError):
        store.create_preset(' ensayo ')


def test_delete_active_preset_returns_to_general_reading():
    store=SettingsStore()
    preset=store.create_preset('Cliente')
    store.replace_preset(preset.id,PresetInput(name='Cliente',defaults=DisplaySettings(speed_px_s=90)))
    store.activate(preset.id)
    assert store.effective('charla',1).speed_px_s==90
    store.delete_preset(preset.id)
    assert store.document.active_preset_id is None
    assert store.effective('charla',1)==DisplaySettings()


@pytest.mark.parametrize('rules',[{0:{}},{-1:{}},{100000:{}},{'abc':{}},{2:{'speed_px_s':-201}}])
def test_invalid_slide_rules_are_rejected(rules):
    with pytest.raises(ValidationError):
        PresetInput(name='Ensayo',rules=rules)


def test_failed_preset_save_preserves_memory_and_disk(tmp_path,monkeypatch):
    from notes_prompter import settings as settings_module
    path=tmp_path/'settings.json'
    store=SettingsStore(path)
    preset=store.create_preset('Antes')
    saved=path.read_text()
    def fail(*_):
        raise OSError('archivo bloqueado')
    monkeypatch.setattr(settings_module.os,'replace',fail)
    with pytest.raises(OSError):
        store.replace_preset(preset.id,PresetInput(name='Después'))
    assert store.get_preset(preset.id).name=='Antes'
    assert path.read_text()==saved


def test_preset_api_and_wire_messages_apply_rules_in_both_directions():
    ctrl=Controller()
    ctrl.add_deck(Deck('charla','charla.pptx',('nota uno','nota dos','nota tres')))
    with TestClient(create_app(ctrl)) as client:
        preset=client.post('/api/admin/presets',json={'name':'Cliente · ensayo'}).json()
        payload=dict(name=preset['name'],presentation='charla',defaults=DisplaySettings(speed_px_s=33).model_dump(),
                     rules={'1':DisplaySettings(speed_px_s=12,start_delay_s=4).model_dump(),
                            '2':DisplaySettings(auto_scroll=False).model_dump()})
        assert client.put('/api/admin/presets/'+preset['id'],json=payload).status_code==200
        assert client.put('/api/admin/active-preset',json={'preset_id':preset['id']}).status_code==200
        with client.websocket_connect('/ws') as ws:
            ws.send_json({'type':'hello','role':'control'})
            first=ws.receive_json(); ws.receive_json()
            assert first['display_settings']['speed_px_s']==12
            assert first['display_settings']['start_delay_s']==4
            ws.send_json({'type':'goto','index':2})
            assert ws.receive_json()['display_settings']['auto_scroll'] is False
            ws.receive_json()
            ws.send_json({'type':'goto','index':3})
            assert ws.receive_json()['display_settings']['speed_px_s']==33
            ws.receive_json()
            ws.send_json({'type':'goto','index':1})
            assert ws.receive_json()['display_settings']['speed_px_s']==12
            ws.receive_json()
        state=client.get('/api/admin/state').json()
        assert state['reading_context']=={'preset':preset['name'],'matches':True,'rule_slide':1}
        assert client.get('/api/display-settings').json()['speed_px_s']==12
        assert client.delete('/api/admin/presets/'+preset['id']).status_code==200
        assert client.get('/api/admin/state').json()['active_preset_id'] is None


def test_binding_a_preset_to_a_different_deck_uses_general_settings():
    store=SettingsStore()
    preset=store.create_preset('Cliente')
    store.replace_preset(preset.id,PresetInput(name='Cliente',presentation='Otra',defaults=DisplaySettings(speed_px_s=70)))
    store.activate(preset.id)
    ctrl=Controller(); ctrl.add_deck(Deck('charla','charla.pptx',('nota',)))
    with TestClient(create_app(ctrl,settings=store)) as client:
        assert client.get('/api/display-settings').json()['speed_px_s']==24
        assert client.get('/api/admin/state').json()['reading_context']['matches'] is False


def test_activating_or_editing_current_rule_notifies_connected_displays():
    ctrl=Controller(); ctrl.add_deck(Deck('charla','charla.pptx',('nota',)))
    with TestClient(create_app(ctrl)) as client:
        preset=client.post('/api/admin/presets',json={}).json()
        with client.websocket_connect('/ws') as ws:
            ws.send_json({'type':'hello','role':'display'}); ws.receive_json()
            assert client.put('/api/admin/active-preset',json={'preset_id':preset['id']}).status_code==200
            assert ws.receive_json()['restart'] is True
            payload=dict(name=preset['name'],defaults=preset['defaults'],rules={'1':DisplaySettings(speed_px_s=9).model_dump()})
            assert client.put('/api/admin/presets/'+preset['id'],json=payload).status_code==200
            message=ws.receive_json()
            assert message['type']=='display_settings' and message['speed_px_s']==9 and message['restart']


def test_missing_and_duplicate_presets_leave_active_selection_unchanged():
    with TestClient(create_app()) as client:
        preset=client.post('/api/admin/presets',json={'name':'Ensayo'}).json()
        assert client.post('/api/admin/presets',json={'name':'ENSAYO'}).status_code==409
        assert client.put('/api/admin/active-preset',json={'preset_id':'inexistente'}).status_code==404
        assert client.delete('/api/admin/presets/inexistente').status_code==404
        assert client.get('/api/admin/state').json()['active_preset_id'] is None
        assert len(client.get('/api/admin/state').json()['presets'])==1


def test_preset_mutations_reject_other_web_origins():
    with TestClient(create_app()) as client:
        assert client.post('/api/admin/presets',json={},headers={'Origin':'https://otra.example'}).status_code==403
