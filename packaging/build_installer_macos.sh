#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${NOTES_PROMPTER_SKIP_BUILD:-0}" != "1" ]]; then
    packaging/build_macos.sh "${1:-.venv/bin/python}"
fi
VERSION="$("${1:-.venv/bin/python}" -c 'from notes_prompter import __version__; print(__version__)')"
DIST_DIR="${NOTES_PROMPTER_DIST_DIR:-dist}"
APP="$DIST_DIR/Notes Prompter.app"
# Inspect the packaged executable, including when reusing an existing build.
ARCH="$(/usr/bin/lipo -archs "$APP/Contents/MacOS/notes-prompter")"
case "$ARCH" in arm64|x86_64) ;; *) printf 'Arquitectura de app no compatible: %s\n' "$ARCH" >&2; exit 1 ;; esac
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/notes-prompter-dmg.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
/usr/bin/ditto --norsrc --noextattr "$APP" "$STAGE/Notes Prompter.app"
# Finder metadata is not part of the signed application payload.
/usr/bin/xattr -d com.apple.FinderInfo "$STAGE/Notes Prompter.app" 2>/dev/null || true
/usr/bin/codesign --verify --deep --strict "$STAGE/Notes Prompter.app"
ln -s /Applications "$STAGE/Applications"
cp README.md "$STAGE/README.md"
cp -R docs "$STAGE/docs"
printf '\nPackage architecture: %s. Intel: x86_64; Apple Silicon: arm64.\n' "$ARCH" >> "$STAGE/README.md"
/usr/bin/hdiutil create -volname "Notes Prompter $VERSION $ARCH" -srcfolder "$STAGE" -ov -format UDZO "$DIST_DIR/Notes-Prompter-$VERSION-macOS-$ARCH.dmg"
printf 'Instalador generado: %s/Notes-Prompter-%s-macOS-%s.dmg\n' "$DIST_DIR" "$VERSION" "$ARCH"
