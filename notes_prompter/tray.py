"""Icono de bandeja y cola de acciones para el hilo principal de Tk."""
from __future__ import annotations

from .i18n import tr

import queue
import sys
import threading


def icon_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 1, 63, 63), radius=14, fill="#007AFF")
    draw.rounded_rectangle((18, 12, 46, 53), radius=4, fill="white")
    for y, end in ((23, 39), (31, 39), (39, 34)):
        draw.line((25, y, end, y), fill="#007AFF", width=3)
    return image


class TrayService:
    def __init__(self):
        self.actions = queue.SimpleQueue()
        self.icon = None
        self.thread = None
        self.error = None
        self.configuration_enabled = True

    @property
    def available(self):
        return bool(self.icon is not None and self.thread is not None
                    and self.thread.is_alive() and self.icon.visible)

    def start(self):
        if sys.platform != "win32":
            return
        try:
            import pystray

            self.icon = pystray.Icon("notes-prompter", icon_image(), "Notes Prompter", pystray.Menu(
                pystray.MenuItem(tr('Abrir'), lambda *_: self.actions.put("open"), default=True),
                pystray.MenuItem(tr('Panel de administración'), lambda *_: self.actions.put("admin"),
                                 enabled=lambda _: self.configuration_enabled),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(tr('Salir'), lambda *_: self.actions.put("exit")),
            ))
            def run():
                try:
                    self.icon.run()
                except (OSError, ValueError) as exc:
                    self.error = str(exc)
            self.thread = threading.Thread(target=run, daemon=True)
            self.thread.start()
        except (ImportError, OSError):
            self.icon = None

    def set_configuration_enabled(self, enabled):
        self.configuration_enabled = bool(enabled)
        if self.available:
            self.icon.update_menu()

    def stop(self):
        if self.icon is not None:
            self.icon.stop()
        if self.thread is not None:
            self.thread.join(3)
