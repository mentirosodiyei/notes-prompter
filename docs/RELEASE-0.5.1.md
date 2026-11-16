# Notes Prompter 0.5.1

Released without a prerelease label. Version 0.5.x remains pre-1.0 software.

- Weekly (7 days, default) or monthly (30 days) GitHub checks; disable or check manually from Application → Updates.
- Last check persists across restarts. Notifications wait while an agent/output is active or the app is hidden.
- Explicit download/install, not now, and skip-version choices. Rejection never changes the installed app.
- HTTPS and GitHub asset SHA256/size verification; correct architecture, complete-asset release selection, no downgrades or prerelease installation.
- Detached updater waits for the app to quit, preserves settings/presets and relaunches. Previous app/EXE retained for replacement and rollback.
- Mac DMG/signature/bundle/minimum-system validation. Windows supports per-user installed and portable copies.
- No elevation, quarantine removal or OS security bypass. Source execution does not self-update.

0.5.0 must be upgraded manually once to obtain the updater. Platform integration tests use disposable copies and synthetic settings; they do not replace real PowerPoint, LAN and monitor testing. Windows EXEs remain unsigned; Mac apps use ad hoc signing without notarization. See the previous [Windows hardware validation boundaries](WINDOWS-VALIDATION-0.5.0.md).

## Verification of this release

- 263 Python tests passed locally on macOS, including weekly/monthly persistence, declined versions, platform asset selection, checksum/size failures and rollback. Two JavaScript renderer regressions remain covered.
- Windows package workflow passed the tests, built the portable EXE and Inno Setup installer, and exercised both frozen update-helper paths using disposable installations and synthetic settings. It verifies replacement, installer execution, relaunch and unchanged settings.
- Apple Silicon and Intel packages were exercised using DMG staging, strict signature/version/architecture checks, frozen detached helper, replacement, retained backup and relaunch in disposable app folders. Intel was tested under Rosetta, not a physical Intel Mac.
- User guide: six pages, updated without a prerelease label. Screenshots show synthetic data only.

The update helper tests use an already-built local artifact, not a fake publicly published release. GitHub metadata selection and streaming checks are tested separately. A future real version-to-version release still needs field testing. Settings are never uploaded to GitHub; the update connection exposes the usual network IP/client version to GitHub.

## Verification for this release

- 263 Python tests passed on the development Mac; source CI passed on Windows, macOS and Linux.
- Windows packages were built on GitHub Actions with Python 3.12 and a SHA256-verified Inno Setup 7.1.1 compiler. Both the portable and installed frozen update helper flows passed against disposable copies, including relaunch and preservation of a settings canary.
- Apple Silicon and Intel packages passed strict signature, architecture, catalog and normal startup checks. Both packaged helper flows passed DMG staging, replacement, backup and relaunch against disposable copies; Intel was exercised under Rosetta.
- The tests use a local package of the same version to exercise replacement. They do not claim an end-to-end public upgrade from 0.5.1 to a future release that does not yet exist. Published asset selection and download integrity have separate tests.
- The updated six-page Spanish user guide was rendered and visually checked. Sources and synthetic screenshots passed the privacy preflight. Hardware and PowerPoint limitations from earlier releases remain applicable.
