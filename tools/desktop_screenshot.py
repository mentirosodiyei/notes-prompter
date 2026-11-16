"""Capture this application's own Cocoa view with synthetic devices (macOS only)."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from notes_prompter import i18n
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--language',choices=['en','ca','es'],default='en');parser.add_argument('--updates',action='store_true');args=parser.parse_args()
i18n.get_language=lambda:args.language
from notes_prompter import gui
from notes_prompter.discovery import Peer
from notes_prompter.screens import Screen
import AppKit
import Foundation
class DemoListener:
    def start(self):pass
    def stop(self):pass
    def join(self,*args):pass
    def peers(self):return [Peer('192.0.2.10',8765,'Demo stage','Conference demo')]
with tempfile.TemporaryDirectory(prefix='np-docs-') as directory, patch.dict(os.environ,{'NOTES_PROMPTER_CONFIG':str(Path(directory)/'settings.json')}), patch.object(gui,'PeerListener',DemoListener), patch.object(gui,'local_addresses',lambda:{'127.0.0.1'}), patch.object(gui,'list_screens',lambda:[Screen(0,0,0,1920,1080,True),Screen(1,1920,0,1920,1080)]):
    root=gui.App()
    try:
        root.geometry('840x720');root.update()
        if args.updates:root.updates.settings()
        for _ in range(8):
            root.update();Foundation.NSRunLoop.currentRunLoop().runMode_beforeDate_(Foundation.NSDefaultRunLoopMode,Foundation.NSDate.dateWithTimeIntervalSinceNow_(.03))
        window=next(window for window in AppKit.NSApplication.sharedApplication().windows() if (str(window.title())==i18n.tr('Actualizaciones') if args.updates else str(window.title()).startswith('Notes Prompter ·')))
        view=window.contentView();image=view.bitmapImageRepForCachingDisplayInRect_(view.bounds());view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(),image)
        data=image.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG,{})
        target=Path(__file__).resolve().parents[1]/'docs/images'/f'{"updates" if args.updates else "desktop"}-{args.language}.png'
        assert data.writeToFile_atomically_(str(target),True)
        from privacy_audit import strip_png_metadata
        strip_png_metadata(target)
        assert root.admin_button.text==i18n.tr('Panel de administración')
        assert not hasattr(root,'live_button')
        print('Captured synthetic desktop UI: '+args.language)
    finally:root._close()
