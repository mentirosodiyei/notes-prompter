import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from notes_prompter import updates as u


def release_data(name='notes-prompter-0.6.0.exe', **asset):
    package={'name':name,'size':4,'digest':'sha256:'+hashlib.sha256(b'test').hexdigest(),
             'browser_download_url':f'https://github.com/{u.REPOSITORY}/releases/download/v0.6.0/{name}'}
    package.update(asset)
    return {'tag_name':'v0.6.0','assets':[package]}


def test_semantic_versions_not_string_order_and_no_downgrades(tmp_path):
    data=release_data()
    assert u.select_release(data,'0.5.9',tmp_path/'app.exe','win32','AMD64').version=='0.6.0'
    for version in ('0.6.0','0.10.0','1.0.0'):
        assert u.select_release(data,version,tmp_path/'app.exe','win32','AMD64') is None
    for key in ('draft','prerelease'):
        assert u.select_release(dict(data,**{key:True}),'0.5.0',tmp_path/'app.exe','win32','AMD64') is None
    with pytest.raises(u.UpdateError):u.version_tuple('v0.6.0-beta.1')


@pytest.mark.parametrize('system,arch,name',[
    ('darwin','arm64','Notes-Prompter-0.6.0-macOS-arm64.dmg'),
    ('darwin','x86_64','Notes-Prompter-0.6.0-macOS-x86_64.dmg'),
    ('win32','AMD64','notes-prompter-0.6.0.exe')])
def test_correct_platform_asset(tmp_path,system,arch,name):
    result=u.select_release(release_data(name),'0.5.1',tmp_path/'app.exe',system,arch)
    assert result.name==name


def test_installed_windows_uses_installer_portable_stays_portable(tmp_path):
    target=tmp_path/'app.exe'
    assert u.asset_name('0.6.0',target,'win32','AMD64')=='notes-prompter-0.6.0.exe'
    (tmp_path/'unins000.exe').touch()
    assert u.asset_name('0.6.0',target,'win32','AMD64')=='Notes-Prompter-Setup-0.6.0.exe'
    with pytest.raises(u.UpdateError):u.asset_name('0.6.0',target,'win32','ARM64')


@pytest.mark.parametrize('asset',[
    {'browser_download_url':'http://github.com/mentirosodiyei/notes-prompter/releases/download/v0.6.0/test.exe'},
    {'browser_download_url':'https://github.com/other/repo/releases/download/v0.6.0/test.exe'},
    {'browser_download_url':'https://github.com.evil.invalid/test.exe'},
    {'digest':None}, {'digest':'sha256:abcd'}, {'size':0}, {'size':u.MAX_DOWNLOAD+1}])
def test_untrusted_or_unverifiable_packages_are_rejected(tmp_path,asset):
    with pytest.raises(u.UpdateError):
        u.select_release(release_data(**asset),'0.5.1',tmp_path/'app.exe','win32','AMD64')


def test_missing_asset_does_not_offer_another_architecture(tmp_path):
    with pytest.raises(u.UpdateError):
        u.select_release(release_data(),'0.5.0',tmp_path/'Notes Prompter.app','darwin','arm64')


class Response(io.BytesIO):
    def geturl(self):return 'https://release-assets.githubusercontent.com/test'


def test_download_streams_and_verifies_hash_before_returning(monkeypatch,tmp_path):
    release=u.select_release(release_data(),'0.5.0',tmp_path/'app.exe','win32','AMD64')
    monkeypatch.setattr(u,'urlopen',lambda *args,**kwargs:Response(b'test'))
    progress=[]
    path=u.download_release(release,tmp_path,progress.append)
    assert path.read_bytes()==b'test'
    assert progress==[1.0]
    assert not list(tmp_path.glob('*.part'))


@pytest.mark.parametrize('content',[b'evil',b'tes',b'test-too-long'])
def test_corrupt_truncated_and_oversized_download_never_reaches_install(monkeypatch,tmp_path,content):
    release=u.select_release(release_data(),'0.5.0',tmp_path/'app.exe','win32','AMD64')
    monkeypatch.setattr(u,'urlopen',lambda *args,**kwargs:Response(content))
    with pytest.raises(u.UpdateError):u.download_release(release,tmp_path)
    assert not list(tmp_path.iterdir())


def test_preferences_persist_skip_disable_and_interval_without_presets(tmp_path):
    path=tmp_path/'updates.json'
    prefs=u.UpdatePreferences.load(path)
    assert prefs.enabled and prefs.days==7
    prefs.enabled=False;prefs.days=30;prefs.last_checked=12345;prefs.skipped='0.6.0';prefs.save(path)
    assert u.UpdatePreferences.load(path)==prefs
    path.write_text('{broken')
    assert u.UpdatePreferences.load(path)==u.UpdatePreferences()
    path.write_text('{"days":0}')
    assert u.UpdatePreferences.load(path)==u.UpdatePreferences()


def test_replacement_keeps_original_backup_and_settings(tmp_path):
    target=tmp_path/'app.exe';target.write_bytes(b'old')
    candidate=tmp_path/'new.exe';candidate.write_bytes(b'new')
    backup=tmp_path/'app.previous.exe';settings=tmp_path/'settings.json';settings.write_bytes(b'private')
    u.replace_with_backup(candidate,target,backup)
    assert target.read_bytes()==b'new' and backup.read_bytes()==b'old'
    assert settings.read_bytes()==b'private'


def test_failed_replacement_restores_original(monkeypatch,tmp_path):
    target=tmp_path/'app.exe';target.write_bytes(b'old')
    candidate=tmp_path/'new.exe';candidate.write_bytes(b'new')
    backup=tmp_path/'app.previous.exe'
    monkeypatch.setattr(u.shutil,'copy2',lambda *args: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):u.replace_with_backup(candidate,target,backup)
    assert target.read_bytes()==b'old' and not backup.exists()


def test_windows_rejects_non_pe_and_wrong_architecture(tmp_path):
    path=tmp_path/'app.exe';path.write_bytes(b'x'*100)
    with pytest.raises(u.UpdateError):u.validate_windows_exe(path)
    data=bytearray(100);data[:2]=b'MZ';data[0x3c:0x40]=(64).to_bytes(4,'little');data[64:70]=b'PE\0\0\x64\x86';path.write_bytes(data)
    u.validate_windows_exe(path)
    data[68:70]=b'\x4c\x01';path.write_bytes(data)
    with pytest.raises(u.UpdateError):u.validate_windows_exe(path)


def test_ui_defers_notice_while_running_or_hidden_and_honors_skipped_version(monkeypatch,tmp_path):
    from notes_prompter import updates_ui as ui
    monkeypatch.setattr(ui,'default_settings_path',lambda:tmp_path/'settings.json')
    monkeypatch.setattr(ui,'installation_target',lambda:tmp_path/'app.exe')
    root=SimpleNamespace(_exiting=False,server=object(),after=lambda *args:None,state=lambda:'normal')
    manager=ui.UpdateManager(root)
    offers=[];monkeypatch.setattr(manager,'offer',lambda:offers.append(True))
    release=u.select_release(release_data(),'0.5.0',tmp_path/'app.exe','win32','AMD64')
    manager.events.put(('checked',release,False));manager.poll();assert not offers
    root.server=None;root.state=lambda:'withdrawn';manager.poll();assert not offers
    root.state=lambda:'normal';manager.poll();assert offers==[True]
    manager.pending=None;offers.clear();manager.preferences.skipped=release.version
    manager.events.put(('checked',release,False));manager.poll();assert not offers


def test_source_execution_does_not_check_network_automatically(monkeypatch,tmp_path):
    from notes_prompter import updates_ui as ui
    monkeypatch.setattr(ui,'default_settings_path',lambda:tmp_path/'settings.json')
    monkeypatch.setattr(ui,'installation_target',lambda:None)
    root=SimpleNamespace(_exiting=False,server=None,after=lambda *args:None,state=lambda:'normal')
    manager=ui.UpdateManager(root);manager.next_check=0
    monkeypatch.setattr(manager,'check',lambda *args:pytest.fail('Unexpected network check'))
    manager.poll()


@pytest.mark.parametrize('days',[7,30])
def test_schedule_survives_restart_and_does_not_recheck_each_launch(monkeypatch,tmp_path,days):
    from notes_prompter import updates_ui as ui
    from types import SimpleNamespace
    monkeypatch.setattr(ui,'default_settings_path',lambda:tmp_path/'settings.json')
    monkeypatch.setattr(ui,'installation_target',lambda:tmp_path/'app.exe')
    monkeypatch.setattr(ui.time,'time',lambda:1000000)
    monkeypatch.setattr(ui.time,'monotonic',lambda:500)
    u.UpdatePreferences(days=days,last_checked=1000000-86400).save(tmp_path/'updates.json')
    root=SimpleNamespace(after=lambda *args:None)
    first=ui.UpdateManager(root)
    second=ui.UpdateManager(root)
    assert first.next_check==second.next_check==500+(days-1)*86400


@pytest.mark.parametrize('report_writable',[True,False])
def test_helper_waits_for_ui_and_bootloader_before_replacing(monkeypatch,tmp_path,report_writable):
    from types import SimpleNamespace
    import sys
    target=tmp_path/'Notes Prompter.app';target.mkdir();(target/'marker').write_text('old')
    candidate=tmp_path/'candidate';candidate.mkdir();(candidate/'marker').write_text('new')
    backup=tmp_path/'previous.app';plan=tmp_path/'plan.json';result=tmp_path/'result.json'
    if not report_writable:
        blocker=tmp_path/'report-blocked';blocker.write_text('keep')
        result=blocker/'result.json'
    plan.write_text(json.dumps({'pid':321,'bootloader_pid':123,'kind':'mac','target':str(target),
                               'candidate':str(candidate),'backup':str(backup),'result':str(result),'version':'0.6.0'}))
    waited=[]
    class FakeProcess:
        def __init__(self,pid):self.pid=pid
        def wait(self,timeout):
            assert (target/'marker').read_text()=='old'
            assert not backup.exists()
            waited.append(self.pid)
    monkeypatch.setitem(sys.modules,'psutil',SimpleNamespace(Process=FakeProcess,NoSuchProcess=ProcessLookupError))
    monkeypatch.setattr(u.sys,'platform','darwin')
    monkeypatch.setattr(u,'validate_mac_app',lambda *args:None)
    relaunched=[]
    monkeypatch.setattr(u.subprocess,'Popen',lambda command,**kwargs:relaunched.append(command))
    assert u.apply_update(plan)==0
    assert waited==[321,123]
    assert (target/'marker').read_text()=='new'
    assert (backup/'marker').read_text()=='old'
    assert relaunched==[['/usr/bin/open','-n',str(target)]]
    if report_writable:
        assert json.loads(result.read_text())['ok']
    else:
        assert blocker.read_text()=='keep'
