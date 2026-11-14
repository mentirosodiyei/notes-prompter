# Build from project root with a Python of the target architecture that includes Tk.
import os
import platform
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH)
version = "0.5.0"
identity = os.environ.get("NOTES_PROMPTER_SIGN_IDENTITY") or None
target_arch = os.environ.get("NOTES_PROMPTER_ARCH", platform.machine())
if target_arch not in {"arm64", "x86_64"}:
    raise ValueError("Se requiere un entorno Python arm64 o x86_64.")
entitlements = str(root / "packaging/entitlements-macos.plist")
a = Analysis(
    [str(root / 'packaging/gui_entry.py')], pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'notes_prompter/static'), 'notes_prompter/static'),
           (str(root / 'notes_prompter/powerpoint_mac.scpt'), 'notes_prompter'),
           (str(root / 'LICENSE'), '.'),
           (str(root / 'notes_prompter/locales'), 'notes_prompter/locales')] + [(str(root / 'packaging' / 'localizations' / (language + '.lproj')), language + '.lproj') for language in ('en','es','ca')],
    hiddenimports=collect_submodules('uvicorn') + collect_submodules('websockets') + ['AppKit','Foundation','WebKit','objc'],
    excludes=['pytest','httpx','Cython','pystray','win32com','pythoncom'],
    noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='notes-prompter',
          console=False, argv_emulation=False, target_arch=target_arch,
          codesign_identity=identity, entitlements_file=entitlements)
coll = COLLECT(exe, a.binaries, a.datas, name='notes-prompter-macos')
app = BUNDLE(coll, name='Notes Prompter.app', icon=str(root / 'packaging/notes-prompter.icns'),
             bundle_identifier='org.notesprompter.desktop',
             info_plist={
                 'CFBundleName': 'Notes Prompter',
                 'CFBundleDevelopmentRegion':'en',
                 'CFBundleLocalizations':['en','ca','es'],
                 'CFBundleDisplayName': 'Notes Prompter',
                 'CFBundleShortVersionString': version,
                 'CFBundleVersion': version,
                 'NSHighResolutionCapable': True,
                 'LSMinimumSystemVersion': '11.0',
                 'NSAppleEventsUsageDescription': 'Reads PowerPoint slides and speaker notes for the prompter without modifying or saving the presentation.',
                 'NSLocalNetworkUsageDescription': 'Discovers agents and shares notes between computers on your local network.',
                 'NSAppTransportSecurity': {'NSAllowsLocalNetworking': True},
             })
