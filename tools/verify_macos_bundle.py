"""Validate a local macOS bundle with temporary settings; does not start PowerPoint."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import time
import AppKit
import Foundation

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('bundle',type=Path)
parser.add_argument('--architecture',choices=['arm64','x86_64'],required=True)
args=parser.parse_args();bundle=args.bundle.resolve()
subprocess.run(['codesign','--verify','--deep','--strict',str(bundle)],check=True)
actual=subprocess.check_output(['lipo','-archs',str(bundle/'Contents/MacOS/notes-prompter')],text=True).strip()
assert actual==args.architecture
info=plistlib.loads((bundle/'Contents/Info.plist').read_bytes())
assert set(info['CFBundleLocalizations'])=={'en','ca','es'}
for lang in ('en','ca','es'):
    file=bundle/'Contents/Resources/notes_prompter/locales'/f'{lang}.json'
    assert file.is_file(),f'Missing {lang} message catalog'
    assert json.loads(file.read_text())
    assert (bundle/'Contents/Resources'/f'{lang}.lproj/InfoPlist.strings').is_file()
def pump():Foundation.NSRunLoop.currentRunLoop().runMode_beforeDate_(Foundation.NSDefaultRunLoopMode,Foundation.NSDate.dateWithTimeIntervalSinceNow_(.1))
with tempfile.TemporaryDirectory(prefix='notes-prompter-bundle-') as folder:
    logfile=Path(folder)/'startup.log'
    with logfile.open('w+') as stream:
        child=subprocess.Popen(['arch','-'+args.architecture,str(bundle/'Contents/MacOS/notes-prompter')],env=dict(os.environ,NOTES_PROMPTER_CONFIG=str(Path(folder)/'settings.json')),stdout=stream,stderr=subprocess.STDOUT)
        try:
            registered=None
            for _ in range(200):
                assert child.poll() is None,'Bundle exited during startup'
                registered=next((app for app in AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_('org.notesprompter.desktop') if app.bundleURL() and Path(app.bundleURL().path())==bundle),None)
                if registered and registered.isFinishedLaunching():break
                pump()
            assert registered
            for _ in range(60):
                if child.poll() is not None or registered.terminate():break
                pump()
            child.wait(10);stream.seek(0);log=stream.read()
            assert child.returncode==0 and 'Traceback' not in log,log
            print(json.dumps({'version':info['CFBundleShortVersionString'],'architecture':actual,'catalogs':['en','ca','es'],'signatureVerified':True,'startedAndClosedNormally':True,'physicalPowerPointTested':False}))
        finally:
            if child.poll() is None:child.terminate();child.wait(5)
