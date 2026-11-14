"""Create an ICNS from the application's existing icon, without external art."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from notes_prompter.tray import icon_image

path = Path(__file__).with_name("notes-prompter.icns")
icon_image().resize((1024, 1024)).save(path, format="ICNS")
