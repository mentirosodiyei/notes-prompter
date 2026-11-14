# Source review and validation notes — 0.5.0

This is a preparation for public source distribution, not a certification that the app is bug-free or an Internet-hardened service.

## Changes made during review

| Issue | Change and evidence |
| --- | --- |
| Damaged settings were silently replaced by defaults and could later be overwritten. | Retain the original file, expose an actionable error and block writes until a valid backup is restored. Tests cover bad JSON, invalid schema and invalid UTF-8, and assert the exact original bytes remain unchanged. |
| Concurrent playback operations could deliver older state after newer state to an output. | Add a monotonic playback revision and ignore older revisions on the output. JavaScript tests execute the shipped renderer with a controlled animation clock and delayed pause/restart messages. |
| The source assumed Spanish in desktop widgets, runtime feedback and web pages. | Explicit English/Catalan/Spanish catalogs, native OS UI-language detection and receiver-selected web language. Tests cover language policy, Windows/macOS selection, catalog/placeholder completeness, static HTML and unchanged user notes/names. |
| A development tree could expose settings, local history, compiled artifacts or real screenshots. | Create a source-only distribution, exclude local files, provide a privacy preflight and generate screenshots using only demo notes/devices. Remove PNG text/EXIF chunks without changing pixel chunks; tests verify the operation. |

Earlier fixes retained include live unsaved Windows note updates, presets bound to PPT name/slide, reversible speed, zero snapping, playback controls only in the panel and macOS output behaviour that does not globally hide the Dock.

## Validation performed

- The existing regression suite, including 150 rules across six presentations and 150 stored presets, remains part of the tests.
- Language selection is tested with OS substitutes. Three actual browser interfaces are rendered using generated notes while the browser has an unrelated language; the receiver's language wins. Notes/preset names remain untouched. Pause/resume and absence of operator buttons in output are checked.
- The actual macOS desktop view is captured in each language with synthetic source/display objects and temporary settings. No real PowerPoint or user settings are used in screenshot generation.
- Source/privacy and documentation links are checked before packaging. The source preflight does not replace manual review or a dedicated binary audit.

Use the command outputs produced for the exact release to establish current test counts; do not treat CI configuration as evidence that all runner platforms have executed it.

## Release boundaries

PowerPoint hardware integration, a physical Mac Intel, Windows GUI/installer execution, LAN conditions, external displays, Spaces/Show Desktop gestures, signing identities and notarization need platform release tests. Intel builds can be checked under Rosetta, but that is not a physical Intel test. There is no Windows executable bundled with this source tree.

This version deliberately remains a trusted-LAN tool without authentication or encryption. Review [SECURITY.md](../SECURITY.md) before using it with real notes. Presentation identity remains normalized file name plus slide index; same-name decks and reordered slides require operator care.
