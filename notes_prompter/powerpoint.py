"""Seguimiento de la presentación abierta en PowerPoint (solo Windows, por COM).

Todas las llamadas COM deben hacerse desde el mismo hilo que inicializó COM.
Por eso `poll()` se invoca desde el bucle del servidor y no desde otro hilo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .notes import Deck

# Tipo ppPlaceholderBody, no posición dentro de la colección.
NOTES_BODY_PLACEHOLDER = 2


@dataclass(frozen=True)
class SlideState:
    deck: Deck
    index: int  # base 1


def _clean_notes(text: str) -> str:
    # PowerPoint separa párrafos con \r y saltos de línea con \v.
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0b", "\n")


def read_slide_notes(slide: Any) -> str:
    """Read the live COM notes body, including edits not saved to disk."""
    try:
        placeholders = slide.NotesPage.Shapes.Placeholders
        for number in range(1, placeholders.Count + 1):
            shape = placeholders(number)
            if shape.PlaceholderFormat.Type == NOTES_BODY_PLACEHOLDER:
                return _clean_notes(shape.TextFrame.TextRange.Text or "")
    except Exception:
        # A slide without a notes body has an empty note.
        pass
    return ""


def read_deck(presentation: Any) -> Deck:
    """Lee el nombre y las notas de un objeto Presentation de COM."""
    notes: list[str] = []
    for position in range(1, presentation.Slides.Count + 1):
        notes.append(read_slide_notes(presentation.Slides(position)))
    return Deck(name=Path(presentation.Name).stem, path=str(presentation.FullName), notes=tuple(notes))


class PowerPointWatcher:
    """Sigue la diapositiva que se proyecta; si no hay proyección, la que está en la ventana de edición."""

    def __new__(cls, app: Any | None = None):
        import sys
        if cls is PowerPointWatcher and sys.platform == "darwin" and app is None:
            from .powerpoint_mac import MacPowerPointWatcher
            return MacPowerPointWatcher()
        return super().__new__(cls)

    def __init__(self, app: Any | None = None) -> None:
        self._app = app  # objeto Application de COM; None hasta conectar
        self._decks: dict[str, Deck] = {}  # caché por ruta completa
        self._com_initialized = False

    def _connect(self) -> Any | None:
        if self._app is not None:
            return self._app
        try:
            import pythoncom
            import win32com.client
        except ImportError:
            return None  # no estamos en Windows o falta pywin32
        if not self._com_initialized:
            pythoncom.CoInitialize()
            self._com_initialized = True
        try:
            self._app = win32com.client.GetActiveObject("PowerPoint.Application")
        except Exception:
            return None  # PowerPoint no está abierto todavía
        return self._app

    def poll(self) -> SlideState | None:
        app = self._connect()
        if app is None:
            return None
        try:
            shows = app.SlideShowWindows
            if shows.Count > 0:
                show = shows(1)
                presentation = show.Presentation
                # Índice real: funciona también con diapositivas ocultas y pases personalizados.
                index = show.View.Slide.SlideIndex
            else:
                presentation = app.ActivePresentation
                index = app.ActiveWindow.View.Slide.SlideIndex
            key = str(presentation.FullName)
            if key not in self._decks or len(self._decks[key].notes) != presentation.Slides.Count:
                self._decks[key] = read_deck(presentation)
            else:
                # The slide count cannot invalidate edited notes. Read the visible
                # slide on every poll, without rescanning the whole deck via COM.
                deck = self._decks[key]
                text = read_slide_notes(presentation.Slides(index))
                if deck.notes[index - 1] != text:
                    notes = list(deck.notes)
                    notes[index - 1] = text
                    self._decks[key] = Deck(deck.name, deck.path, tuple(notes))
            return SlideState(deck=self._decks[key], index=index)
        except Exception:
            # PowerPoint cerrado u ocupado: el siguiente sondeo vuelve a conectar.
            self._app = None
            self._decks.clear()
            return None

    def close(self) -> None:
        """Libera COM desde el mismo hilo que hizo los sondeos."""
        self._app = None
        self._decks.clear()
        if self._com_initialized:
            import pythoncom

            pythoncom.CoUninitialize()
            self._com_initialized = False
