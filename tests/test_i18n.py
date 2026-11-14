import json
import re
import sys
from collections import Counter
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from notes_prompter import i18n
from notes_prompter.notes import Deck
from notes_prompter.server import create_app
from notes_prompter.state import Controller
from notes_prompter.settings import SettingsStore,DisplaySettings


@pytest.mark.parametrize('tag,expected',[('ca-ES','ca'),('ca_ES','ca'),('es-MX','es'),('es_ES','es'),('en-CA','en'),('fr-ES','en'),('de-DE','en'),('', 'en'),(None,'en')])
def test_language_policy(tag,expected):
    assert i18n.language_for(tag)==expected


@pytest.mark.system_language
@pytest.mark.parametrize('tag,expected',[('ca-ES','ca'),('es-ES','es'),('en-US','en'),('fr-FR','en')])
def test_macos_uses_preferred_ui_language(monkeypatch,tag,expected):
    monkeypatch.setattr(sys,'platform','darwin')
    monkeypatch.setitem(sys.modules,'Foundation',SimpleNamespace(NSLocale=SimpleNamespace(preferredLanguages=lambda:[tag])))
    i18n.get_language.cache_clear()
    try:assert i18n.get_language()==expected
    finally:i18n.get_language.cache_clear()


@pytest.mark.system_language
@pytest.mark.parametrize('identifier,expected',[(0x0403,'ca'),(0x0803,'ca'),(0x0c0a,'es'),(0x0809,'en'),(0x040c,'en')])
def test_windows_uses_ui_language_not_browser_or_region(monkeypatch,identifier,expected):
    import ctypes
    monkeypatch.setattr(sys,'platform','win32')
    monkeypatch.setattr(ctypes,'windll',SimpleNamespace(kernel32=SimpleNamespace(GetUserDefaultLocaleName=lambda *args:1,GetUserDefaultUILanguage=lambda:identifier)),raising=False)
    i18n.get_language.cache_clear()
    try:assert i18n.get_language()==expected
    finally:i18n.get_language.cache_clear()


def test_catalogs_have_identical_messages_and_preserve_every_placeholder():
    original=i18n.catalog('es')
    assert len(original)>=300
    for language in ('en','ca'):
        translated=i18n.catalog(language)
        assert translated.keys()==original.keys()
        for key,value in translated.items():
            assert value.strip()
            assert Counter(re.findall(r'\{\d+\}',key))==Counter(re.findall(r'\{\d+\}',value)),key


@pytest.mark.parametrize('language,heading',[('en','Administration panel'),('es','Panel de administración'),('ca','Panell d’administració')])
def test_web_uses_receiver_language_and_leaves_user_content_unchanged(monkeypatch,language,heading):
    monkeypatch.setattr(i18n,'get_language',lambda:language)
    ctrl=Controller();ctrl.add_deck(Deck('Pausar','demo.pptx',('Volver al principio {0} <b>notes</b>',)))
    with TestClient(create_app(ctrl)) as client:
        response=client.get('/admin')
        assert response.headers['Content-Language']==language
        assert f'<html lang="{language}">' in response.text
        assert f'<h1>{heading}</h1>' in response.text
        assert '/static/i18n.js' in response.text
        assert client.get('/api/admin/state').json()['language']==language
        preset=client.post('/api/admin/presets',json={'name':'Pausar'}).json()
        assert preset['name']=='Pausar'
        copy=client.post('/api/admin/presets',json={'copy_from':preset['id']}).json()
        assert copy['name']=='Pausar '+{'en':'(copy)','es':'(copia)','ca':'(còpia)'}[language]
        with client.websocket_connect('/ws') as ws:
            ws.send_json({'type':'hello','role':'display'})
            message=ws.receive_json()
            assert message['presentation']=='Pausar'
            assert message['notes']=='Volver al principio {0} <b>notes</b>'


def test_user_values_are_not_translated_or_interpolated_twice(monkeypatch):
    monkeypatch.setattr(i18n,'get_language',lambda:'en')
    assert i18n.tr('{0} guardada en {1}.','Pausar {1}','Program')=='Pausar {1} saved in Program.'


def test_catalog_bootstrap_cannot_close_its_script_element(monkeypatch):
    monkeypatch.setattr(i18n,'get_language',lambda:'en')
    monkeypatch.setattr(i18n,'catalog',lambda _: {'x':'</script><img src=x>'})
    html=i18n.localized_html('<html lang="es"><head></head><body></body></html>')
    assert '</script><img' not in html
    assert '\\u003c/script>' in html


@pytest.mark.parametrize('content',[b'not JSON',b'\xff',b'{"version":3,"presets":"invalid"}'])
def test_damaged_settings_are_visible_and_cannot_be_overwritten(tmp_path,content):
    path=tmp_path/'settings.json';path.write_bytes(content)
    store=SettingsStore(path)
    assert store.load_error
    with pytest.raises(OSError):store.update(DisplaySettings())
    with TestClient(create_app(settings=store)) as client:
        assert client.get('/api/admin/state').json()['settings_error']
        assert client.put('/api/admin/display-settings',json={'min_font_px':60}).status_code==503
    assert path.read_bytes()==content


@pytest.mark.parametrize('language,choose,next_label,goto',[
    ('es','Elegir archivo PowerPoint…','Siguiente ›','Ir a'),
    ('ca','Tria un fitxer PowerPoint…','Següent ›','Anar a'),
    ('en','Choose PowerPoint file…','Next ›','Go to')])
def test_file_picker_and_manual_navigation_follow_receiver_language(monkeypatch,language,choose,next_label,goto):
    monkeypatch.setattr(i18n,'get_language',lambda:language)
    with TestClient(create_app()) as client:
        assert f'>{choose}</button>' in client.get('/admin').text
        control=client.get('/control').text
        assert next_label in control
        assert goto in control


def test_all_static_interface_text_is_in_catalog():
    from html.parser import HTMLParser
    from pathlib import Path
    allowed={'Notes Prompter','48 px','24 px/s','P','R'}
    missing=[]
    class Text(HTMLParser):
        skip=False
        def handle_starttag(self,tag,attrs):
            if tag in ('script','style'):self.skip=True
        def handle_endtag(self,tag):
            if tag in ('script','style'):self.skip=False
        def handle_data(self,data):
            value=data.strip()
            if not self.skip and any(c.isalpha() for c in value) and value not in allowed and value not in i18n.catalog('es'):
                missing.append(value)
    for page in (Path(i18n.__file__).parent/'static').glob('*.html'):
        Text().feed(page.read_text(encoding='utf-8'))
    assert not missing,missing
