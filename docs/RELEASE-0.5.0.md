# 0.5.0 beta 1 - release status

The application version is 0.5.0. The GitHub prerelease tag is v0.5.0-beta.1. Platform packages are separate assets; do not use the Intel package on an Apple Silicon Mac.

## Integrated changes

- English/Catalan/Spanish selected by the operating system UI language; unsupported languages use English. Web pages follow the receiver. User content remains unchanged.
- Per-presentation and per-slide presets, live font size and reversible speed, magnetic zero, pause and restart in the administration panel only.
- Preserve corrupt settings and block writes; ignore delayed playback revisions.
- Windows broadcast fallback from active interface address/netmask; additional translations for file selection/manual navigation.
- Optional Companion module 1.0.3 source and package for Companion 5.1.1, targeting the Listen receiver on port 8765. Pause/restart actions are not implemented by this module.

## Evidence and boundaries

The Windows producer reports 237 passing Python tests, one macOS-only skip, two passing renderer tests, verified AMD64 GUI executables and embedded catalogs. See [the original platform report](WINDOWS-VALIDATION-0.5.0.md), including the distinction between its initial installed build and final translation rebuild. Do not treat it as validation of local Windows PowerPoint COM or all hardware paths.

The merged source was checked on macOS: 237 tests passed on the first run and one discovery test hit a temporary port collision; that test passed when rerun. Two renderer tests passed. macOS packages were rebuilt from this merged application source and their signatures, architectures, catalogs and startup checked. Intel startup was checked under Rosetta, not physical Intel hardware.

Windows executables have no Authenticode signature. macOS uses ad hoc signing without notarization. The PDF guide explains beta installation, checks and reporting without disabling platform protections.

Physical PowerPoint integration, unsaved note edits on Windows, real UI languages on Windows, multi-monitor/DPI/Spaces behaviour, network reconnection and update/uninstall preservation still require beta tests. The tool uses plaintext unauthenticated trusted-LAN communication. Presentation identity is normalized file name plus slide index; same-name decks and reordered slides require care.

The Companion module passed all 19 tests against the merged 0.5.0 API and the real Companion 5.1.1 connection runtime, using synthetic loopback data. Two test assertions were updated to accept localized feedback; the module runtime code is unchanged. Real surfaces/knobs still need beta testing.

Source, screenshots and demo data were reviewed for personal information. The app module code filenames inside all three portable/frozen executables were checked and contain no user-home paths. Binary inspection is separate from the source privacy audit; no audit is a guarantee against all possible sensitive data.
