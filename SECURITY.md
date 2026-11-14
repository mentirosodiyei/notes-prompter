# Security and data handling

Notes Prompter is intended for a trusted, isolated event LAN. It is not an Internet service.

- TCP 8765 provides HTTP configuration and WebSocket speaker notes; UDP 8766 announces agents.
- There is no authentication, authorization by user account, TLS or end-to-end encryption. Other devices on the LAN may read notes and change receiver settings. Same-origin checks reduce browser-origin attacks but are not authentication; Companion intentionally calls the API directly.
- Discovery includes the computer name and presentation name. Current speaker notes are sent to the receiver. PowerPoint files themselves are not transferred by an Agent. Importing a PPTX for metadata sends that file to the selected receiver for inspection.
- The app has no telemetry or external account service. User settings are stored locally and can contain presentation and preset names. Never commit settings, real presentations or event screenshots.
- PowerPoint integration reads notes/slide position and does not save or modify presentations. Windows uses COM; macOS uses Apple Events and needs Automation permission only on a local Agent.
- A malformed settings file is preserved. The app shows an error and blocks writes until a valid backup is restored and the app restarted. Keep separate backups of valuable presets.
- Local builds use ad-hoc signing on macOS and are not notarized. This repository does not claim a security audit or signed Windows release.

Do not forward these ports, expose the service publicly, or use it on an untrusted shared Wi-Fi network. Use network isolation for event equipment. The installer does not change firewall, VPN or startup settings.

Before a release, run the tests and `python tools/privacy_audit.py`, review screenshots, and inspect any executable separately. The source privacy check is not a binary/secret-scanner certification. If reporting a vulnerability, use the repository's private reporting facility when available and avoid attaching real speaker notes or credentials to a public issue.
