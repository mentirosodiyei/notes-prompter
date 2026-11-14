# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path

hiddenimports = []
hiddenimports += collect_submodules('win32com')
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('websockets')
hiddenimports += collect_submodules('screeninfo')
hiddenimports += collect_submodules('pystray')


a = Analysis(
    ['packaging/gui_entry.py'],
    pathex=[str(Path(SPECPATH))],
    binaries=[],
    datas=[('notes_prompter/static', 'notes_prompter/static'), ('notes_prompter/locales', 'notes_prompter/locales')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='notes-prompter',
    icon=str(Path(SPECPATH) / 'packaging' / 'notes-prompter.ico'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
