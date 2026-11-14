NOTES PROMPTER

Agent reads speaker notes from the local PowerPoint and sends them over the LAN.
Listen receives notes, applies presets and displays the prompter on a selected screen.
Only Listen has the Administration panel. Connect Companion to that receiver, port 8765.

Link a preset to each PowerPoint and save its per-slide rules. Automatic selection
uses the presentation file name and slide number. Use distinct names for different decks.

UI language follows the operating system: Catalan, Spanish or English for all others.
Notes and user-entered names are not translated.

Use Application > Quit before updating. Closing the window keeps the app running.
The installer preserves settings in %LOCALAPPDATA%\NotesPrompter\settings.json.
Windows requires PowerPoint for the local Agent and Chrome/Edge for Listen output.

Use a trusted LAN: TCP 8765 and UDP 8766 are unauthenticated and unencrypted.
Do not expose the service to the Internet. No firewall rules are changed.
