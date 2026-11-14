# Contributing

Use Python 3.11+ (the build/test baseline is Python 3.12). See [BUILD.md](docs/BUILD.md).

## Tests

```sh
python -m pytest -q
node --test tests/browser/playback.test.cjs
python tools/privacy_audit.py
```

Tests use temporary files and synthetic presentations. Most tests pin the legacy Spanish messages; `system_language` tests exercise the real language-selection function with platform substitutes. No Windows COM hardware test is implied by a mocked `win32` platform.

## Translations

UI messages are explicit source strings, with matching keys in `notes_prompter/locales/es.json`, `ca.json` and `en.json`. Add every message to all three catalogs. Keep every numbered placeholder such as `{0}` intact; tests validate key and placeholder parity.

Python uses `tr(message, *values)` and JavaScript uses `tr(message, ...values)`. The receiver renders static HTML and supplies its own catalog to the browser. Never translate incoming notes, file names or user-entered preset names. Never scan arbitrary DOM text to translate it. Keep protocol field names and stored settings language-independent.

Language selection reads macOS preferred UI languages, Windows' user UI language, or the locale on other development systems. Only `ca` and `es` are mapped specially; all others use `en`. Documentation tools can simulate a language without changing operating-system preferences.

## Documentation screenshots

Install Playwright locally (`npm install --no-save playwright`, then `npx playwright install chromium`). With the Python environment in `.venv`:

```sh
node tools/screenshots.cjs
```

`NP_DEMO_PYTHON` can point to another Python environment; `NP_SCREENSHOT_CHANNEL=chrome` uses an installed Chrome in an isolated automation profile. The local demo binds only to loopback and uses generated notes/in-memory settings. It does not open PowerPoint or discover real devices. For the desktop screenshots on macOS:

```sh
python tools/desktop_screenshot.py --language en
python tools/desktop_screenshot.py --language ca
python tools/desktop_screenshot.py --language es
```

The desktop capture renders only the application's own Cocoa view with synthetic source/display objects, not the screen or other applications. Check screenshots manually for clipping and sensitive content before committing them.

## Public contributions

Do not add personal paths, names of real event machines, account addresses, tokens, settings files, presentation files or development reports. Test addresses should be synthetic. The license and screenshots belong with the source; generated installers belong in Releases. Do not suppress failed tests to make a release appear verified.
