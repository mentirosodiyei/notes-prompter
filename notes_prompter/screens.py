"""Pantallas disponibles y navegador en modo kiosco para la salida de la nota."""

from __future__ import annotations

from .i18n import tr

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Screen:
    index: int
    x: int
    y: int
    width: int
    height: int
    primary: bool = False

    @property
    def label(self) -> str:
        tag = tr(" (principal)") if self.primary else ""
        return tr('Pantalla {0}: {1}x{2} en {3},{4}{5}', f'{self.index + 1}', f'{self.width}', f'{self.height}', f'{self.x}', f'{self.y}', f'{tag}')


def list_screens() -> list[Screen]:
    if sys.platform == "darwin":
        from AppKit import NSScreen
        native = NSScreen.screens()
        if not native:
            return []
        top = native[0].frame().origin.y + native[0].frame().size.height
        return [screen_from_cocoa(i, item.frame(), top) for i, item in enumerate(native)]
    from screeninfo import get_monitors

    screens = []
    for i, m in enumerate(get_monitors()):
        screens.append(
            Screen(index=i, x=m.x, y=m.y, width=m.width, height=m.height, primary=bool(m.is_primary))
        )
    return screens


def screen_from_cocoa(index, frame, primary_top):
    # Cocoa points, not Retina pixels. Convert bottom-left to top-left once.
    return Screen(index, round(frame.origin.x), round(primary_top - frame.origin.y - frame.size.height),
                  round(frame.size.width), round(frame.size.height), index == 0)


def find_browser() -> str | None:
    """Chrome o Edge. Edge viene con Windows, así que casi siempre hay uno disponible."""
    candidates: list[Path] = []
    for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if not base:
            continue
        candidates.append(Path(base) / "Google/Chrome/Application/chrome.exe")
        candidates.append(Path(base) / "Microsoft/Edge/Application/msedge.exe")
    for path in candidates:
        if path.is_file():
            return str(path)
    for name in ("chrome", "google-chrome", "msedge", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    for base in (Path("/Applications"), Path.home() / "Applications"):
        for name in ("Google Chrome", "Microsoft Edge"):
            path = base / f"{name}.app/Contents/MacOS/{name}"
            if path.is_file():
                return str(path)
    return None


def kiosk_command(browser: str, url: str, screen: Screen | None, profile_dir: str) -> list[str]:
    """Comando para abrir `url` en modo kiosco, en la posición de `screen`.

    `profile_dir` separado hace que Chrome abra una ventana nueva, en lugar de reutilizar
    una sesión ya abierta, que ignoraría la posición.
    """
    cmd = [browser, "--kiosk", "--no-first-run", f"--user-data-dir={profile_dir}"]
    if Path(browser).name.lower() in {"msedge", "msedge.exe"}:
        cmd.append("--edge-kiosk-type=fullscreen")
    if screen is not None:
        cmd.append(f"--window-position={screen.x},{screen.y}")
    cmd.append(url)
    return cmd
