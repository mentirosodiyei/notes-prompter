#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${1:-.venv/bin/python}"
ARCH="$("$PYTHON" -c 'import platform,sys,tkinter; assert sys.version_info >= (3,11); print(platform.machine())')"
case "$ARCH" in arm64|x86_64) ;; *) printf 'Arquitectura de Python no compatible: %s\n' "$ARCH" >&2; exit 1 ;; esac
export NOTES_PROMPTER_ARCH="$ARCH"
DIST_DIR="${NOTES_PROMPTER_DIST_DIR:-dist}"
BUILD_DIR="${NOTES_PROMPTER_BUILD_DIR:-build/macos-$ARCH}"
# Compile against the installed dictionary. Listener-only target Macs do not need PowerPoint.
/usr/bin/osacompile -o notes_prompter/powerpoint_mac.scpt notes_prompter/powerpoint_mac.applescript
"$PYTHON" packaging/make_macos_icon.py
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$PWD/build/pyinstaller-cache}"
"$PYTHON" -m PyInstaller --noconfirm --clean --distpath "$DIST_DIR" --workpath "$BUILD_DIR" notes-prompter-macos.spec
/usr/bin/codesign --verify --deep --strict "$DIST_DIR/Notes Prompter.app"
printf 'Aplicación %s generada: %s/Notes Prompter.app\n' "$ARCH" "$DIST_DIR"
