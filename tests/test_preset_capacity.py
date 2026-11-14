from fastapi.testclient import TestClient

from notes_prompter.notes import Deck
from notes_prompter.server import create_app
from notes_prompter.settings import DisplaySettings, PresetInput, SettingsStore
from notes_prompter.state import Controller


def reading(ppt, slide):
    return DisplaySettings(font_mode='fixed', min_font_px=24+ppt*25+slide,
                           speed_px_s=-75+ppt*25+slide, start_delay_s=slide % 5)


def test_six_powerpoints_150_slide_rules_auto_select_on_wire_after_restart(tmp_path):
    path=tmp_path/'settings.json';store=SettingsStore(path);ctrl=Controller();ids={}
    for ppt in range(6):
        name=f'Congreso {ppt+1}'
        store.remember_presentation(name,25)
        preset=store.create_preset(f'Programa {name}')
        store.replace_preset(preset.id,PresetInput(name=preset.name,
            presentation=f'CONGRESO {ppt+1}.PPTX',presentation_total=25,
            rules={slide:reading(ppt,slide) for slide in range(1,26)}))
        ids[name]=preset.id
        ctrl.add_deck(Deck(name,f'{name}.pptx',tuple(f'Nota {n}' for n in range(1,26))))
    restored=SettingsStore(path)
    assert restored.document.auto_select_presentation
    assert restored.document.active_preset_id is None
    assert sum(len(p.rules) for p in restored.document.presets)==150
    with TestClient(create_app(ctrl,settings=restored)) as client, client.websocket_connect('/ws') as ws:
        ws.send_json({'type':'hello','role':'control'});ws.receive_json();ws.receive_json()
        # Reverse traversal catches values incorrectly carried over from the previous PPT/slide.
        for ppt in reversed(range(6)):
            name=f'Congreso {ppt+1}'
            ws.send_json({'type':'select','presentation':name});ws.receive_json();ws.receive_json()
            for slide in reversed(range(1,26)):
                ws.send_json({'type':'goto','index':slide})
                message=ws.receive_json();ws.receive_json()
                assert (message['presentation'],message['index'],message['total'])==(name,slide,25)
                assert message['display_settings']==reading(ppt,slide).model_dump()
            state=client.get('/api/admin/state').json()
            assert state['effective_preset_id']==ids[name]
            assert state['reading_context']['rule_slide']==1
        assert restored.effective('Sin programa',1)==DisplaySettings()
    again=SettingsStore(path)
    assert sum(len(p.rules) for p in again.document.presets)==150
    for ppt in range(6):
        for slide in range(1,26):
            assert again.effective(f'congreso {ppt+1}.pptx',slide)==reading(ppt,slide)


def test_150_named_presets_keep_rules_and_preferred_variant_for_each_ppt(tmp_path):
    path=tmp_path/'many.json';store=SettingsStore(path);expected={};chosen={}
    for ppt in range(6):store.remember_presentation(f'PPT {ppt+1}',25)
    for number in range(150):
        ppt,variant=divmod(number,25)
        preset=store.create_preset(f'Programa {number+1}')
        settings=reading(ppt,variant+1)
        store.replace_preset(preset.id,PresetInput(name=preset.name,
            presentation=f'PPT {ppt+1}',presentation_total=25,rules={variant+1:settings}))
        expected[preset.id]=(variant+1,settings)
        chosen[ppt]=preset.id
    # Remember one chosen programme per PPT, independently of the last global activation.
    for preset_id in chosen.values():store.activate(preset_id)
    restored=SettingsStore(path)
    assert len(restored.document.presets)==150
    for preset_id,(slide,settings) in expected.items():
        assert restored.get_preset(preset_id).rules[slide]==settings
    for ppt,preset_id in chosen.items():
        assert restored.effective_preset_id(f'PPT {ppt+1}.pptx')==preset_id
        assert restored.effective(f'PPT {ppt+1}',25)==reading(ppt,25)
    _,settings=expected[chosen[0]]
    assert restored.effective('PPT 1',1)==DisplaySettings()  # Missing rules use that programme's defaults.
    with TestClient(create_app(settings=restored)) as client:
        state=client.get('/api/admin/state').json()
        assert len(state['presets'])==150
        assert sum(len(p['rules']) for p in state['presets'])==150
