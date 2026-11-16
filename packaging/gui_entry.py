"""Frozen desktop entry point, including the detached updater helper."""
import sys

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--apply-update':
        from pathlib import Path
        from notes_prompter.updates import apply_update
        raise SystemExit(apply_update(Path(sys.argv[2])))
    from notes_prompter.gui import main
    main()
