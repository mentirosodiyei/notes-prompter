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
