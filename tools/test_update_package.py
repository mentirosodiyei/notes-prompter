"""Exercise the packaged update helper only against disposable application copies.

Never installs over the real application, starts PowerPoint or reads user settings.
macOS: --mac-app path/to/app --mac-dmg path/to/dmg
Windows: --windows-exe path/to/exe --windows-installer path/to/setup
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from notes_prompter import __version__
from notes_prompter import updates

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mac-app', type=Path)
parser.add_argument('--mac-dmg', type=Path)
parser.add_argument('--windows-exe', type=Path)
parser.add_argument('--windows-installer', type=Path)
args = parser.parse_args()


def stop_test_apps(folder):
    for proc in psutil.process_iter(['exe']):
        try:
            exe = proc.info.get('exe')
            if exe and Path(exe).resolve().is_relative_to(folder.resolve()):
                proc.terminate()
                try:proc.wait(10)
                except psutil.TimeoutExpired:proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):pass


def wait_result(path):
    deadline = time.monotonic() + 100
    while time.monotonic() < deadline:
        try:return json.loads(path.read_text())
        except (OSError, ValueError):time.sleep(.2)
    raise AssertionError('Packaged updater did not return a result')


with tempfile.TemporaryDirectory(prefix='notes-prompter-update-check-') as temp:
    folder = Path(temp)
    env = dict(os.environ, NOTES_PROMPTER_CONFIG=str(folder/'settings.json'), PYINSTALLER_RESET_ENVIRONMENT='1')
    # Canary data must remain byte-identical; the updater has no reason to read it.
    settings = folder/'settings.json'
    settings.write_bytes(b'{"version":3,"display_settings":{},"presets":[]}')
    before = settings.read_bytes()
    try:
        if args.mac_app:
            assert args.mac_dmg
            target = folder/'install/Notes Prompter.app'
            target.parent.mkdir()
            updates.run(['/usr/bin/ditto','--norsrc','--noextattr',str(args.mac_app.resolve()),str(target)])
            release = updates.Release(__version__,args.mac_dmg.name,
                                      'https://github.com/mentirosodiyei/notes-prompter/releases/download/v'+__version__+'/'+args.mac_dmg.name,
                                      args.mac_dmg.stat().st_size,hashlib.sha256(args.mac_dmg.read_bytes()).hexdigest())
            # The test uses a local verified artifact instead of publishing a fake release.
            original = updates.download_release
            def local_download(release, stage, progress):
                destination=stage/release.name
                shutil.copyfile(args.mac_dmg,destination)
                assert hashlib.sha256(destination.read_bytes()).hexdigest()==release.sha256
                return destination
            updates.download_release=local_download
            plan = updates.prepare_plan(release,target,folder/'result.json')
            updates.download_release=original
            data=json.loads(plan.read_text());data['pid']=2147483647
            plan.write_text(json.dumps(data))
            helper=Path(data['stage'])/'helper.app/Contents/MacOS/notes-prompter'
            child=subprocess.Popen([str(helper),'--apply-update',str(plan)],env=env)
            assert wait_result(folder/'result.json')['ok']
            assert Path(data['backup']).is_dir()
            assert target.is_dir()
            child.wait(15)
            time.sleep(3)
            stop_test_apps(folder)
            print('macOS: DMG staging, packaged helper, replacement, backup and relaunch verified')
        else:
            assert sys.platform=='win32' and args.windows_exe and args.windows_installer
            exe=args.windows_exe.resolve();installer=args.windows_installer.resolve()
            for kind in ('portable','installer'):
                install=folder/kind;install.mkdir()
                target=install/'notes-prompter.exe'
                if kind=='installer':
                    updates.run([str(installer),'/VERYSILENT','/SUPPRESSMSGBOXES','/SP-','/NORESTART','/CURRENTUSER','/DIR='+str(install)])
                    assert (install/'unins000.exe').is_file()
                else:shutil.copy2(exe,target)
                stage=folder/(kind+'-helper');stage.mkdir()
                helper=stage/'helper.exe';shutil.copy2(exe,helper)
                candidate=installer if kind=='installer' else exe
                result=folder/(kind+'-result.json')
                plan=stage/'plan.json'
                data={'pid':2147483647,'kind':kind,'target':str(target),'candidate':str(candidate),
                      'stage':str(stage),'version':__version__,'sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),
                      'result':str(result),'backup':str(install/'previous.exe')}
                plan.write_text(json.dumps(data))
                child=subprocess.Popen([str(helper),'--apply-update',str(plan)],env=env)
                assert wait_result(result)['ok'],kind
                assert hashlib.sha256(target.read_bytes()).digest()==hashlib.sha256(exe.read_bytes()).digest()
                if kind=='portable':assert Path(data['backup']).is_file()
                child.wait(15)
                time.sleep(4)
                stop_test_apps(install)
                if kind=='installer':
                    time.sleep(2)
                    updates.run([str(install/'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'])
                print('Windows '+kind+': packaged helper, update and relaunch verified')
        assert settings.read_bytes()==before,'Updater changed the settings canary'
    finally:
        stop_test_apps(folder)
