# Build and release

## Source environment

From the repository root, create and activate a Python 3.11+ virtual environment. Python 3.12 is the tested baseline.

```sh
python -m venv .venv
# macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,build]"
python -m pytest -q
node --test tests/browser/playback.test.cjs
python tools/privacy_audit.py
```

Packaged apps include Python. Running from source requires the environment above. To launch the GUI, use **`notes-prompter-gui`** (installed by pip), or `python packaging/gui_entry.py` from this root. The module `python -m notes_prompter` runs the legacy standalone HTTP service, not the desktop role selector.

## macOS

Use a Python runtime of the desired architecture with Tk. Install the project's dependencies and PyInstaller. `packaging/requirements-macos-build.txt` records the tested build environment; do not mix arm64 and x86_64 binary dependencies.

```sh
packaging/build_macos.sh .venv/bin/python
packaging/build_installer_macos.sh .venv/bin/python
```

For a separate architecture-specific output folder:

```sh
NOTES_PROMPTER_DIST_DIR=dist/macos-x86_64 packaging/build_installer_macos.sh .venv-intel/bin/python
```

The script detects the Python architecture. Intel builds can be made using an x86_64 Python under Rosetta, but still require testing on physical Intel hardware. The macOS minimum declared by the bundle is 11.0; check that all native dependencies satisfy that minimum when changing build dependencies.

Building the AppleScript resource requires PowerPoint's scripting dictionary on the build Mac. A packaged Listen receiver does not require PowerPoint. The compiled `.scpt` is generated locally and ignored by Git; the readable `.applescript` source is included. Language catalogs and native `InfoPlist.strings` must be included in the bundle; both specs include them.

Default signing is ad-hoc. `NOTES_PROMPTER_SIGN_IDENTITY` can select a signing identity already available to the builder. Developer ID distribution and notarization require a separate release process and credentials; no credentials are part of the repository.

## Windows

Build on Windows x64 with Python/Tk, project dependencies, PyInstaller and Inno Setup 7 x64:

```bat
packaging\build_windows.bat ".venv\Scripts\python.exe"
packaging\build_installer_windows.bat "C:\Program Files (x86)\Inno Setup 7\ISCC.exe" ".venv\Scripts\python.exe"
```

Use the actual compiler path on the build machine. The scripts produce `dist\notes-prompter.exe` and `dist\Notes-Prompter-Setup-0.5.0.exe`. Source files do not mean these executables have already been built or tested on Windows.

The installer selects English, Catalan or Spanish using the Windows UI language; unsupported languages fall back to English. It needs the standard Inno Setup Catalan/Spanish language files. The language policy uses [LanguageDetectionMethod](https://jrsoftware.org/inno-setup/documentation/topic_setup_languagedetectionmethod.htm) and [ShowLanguageDialog](https://jrsoftware.org/inno-setup/documentation/topic_setup_showlanguagedialog.htm). Validate the full installer and uninstall flow on Windows before releasing it.

## Release checklist

1. Run Python and JavaScript tests and the source privacy audit.
2. Regenerate/review screenshots using only demo data. Review all three languages, including dynamic feedback and dialogs.
3. Build each native package and verify its architecture/signature and included language catalogs. Test launch and closing with temporary settings.
4. Test PowerPoint editing and slideshow modes, unsaved note changes, switching PPTs, presets after restart, keyboard/wheel controls and multiple real displays.
5. Test LAN discovery/reconnection and any supported Companion module against the exact binary release.
6. Back up settings before an installation test. Confirm updates/uninstall preserve them.
7. Inspect binaries separately for embedded personal paths/metadata and platform-specific issues. Attach only verified binaries to Releases. Keep local logs, environments and user settings out of Git.

There is a CI workflow for source tests and the privacy audit. CI does not exercise physical PowerPoint, desktop gestures or signing/notarization credentials.

If macOS adds Finder/File Provider metadata in a cloud-synced checkout, build and sign outside that synced folder. For example, set `NOTES_PROMPTER_DIST_DIR` and `NOTES_PROMPTER_BUILD_DIR` to architecture-specific folders under the system temporary directory. Do not remove quarantine or disable platform protections to work around signing failures. Verify the clean bundle and final DMG with `codesign --verify --deep --strict` and `hdiutil verify`.
