"""Estado del emisor: presentaciones cargadas, la activa y la diapositiva actual."""

from __future__ import annotations

from .i18n import tr

from .notes import Deck, load_deck
from .protocol import ProtocolError, slide_message


class Controller:
    def __init__(self) -> None:
        self._decks: dict[str, Deck] = {}
        self._active: str | None = None
        self._index = 1

    @property
    def names(self) -> list[str]:
        return list(self._decks)

    @property
    def active_name(self) -> str | None:
        return self._active

    def clear(self) -> None:
        """Borra el estado cuando desaparece la presentación seguida."""
        self._decks.clear()
        self._active = None
        self._index = 1

    def load(self, path: str) -> Deck:
        """Carga un .pptx. Si ya había una con el mismo nombre, la reemplaza."""
        deck = load_deck(path)
        self.add_deck(deck)
        return deck

    def add_deck(self, deck: Deck) -> None:
        """Registra una presentación ya leída (de archivo o de PowerPoint).
        Si no hay ninguna activa, esta pasa a serlo."""
        self._decks[deck.name] = deck
        if self._active is None:
            self._active = deck.name
        if self._active == deck.name:
            self._index = min(self._index, deck.total) if deck.total else 1

    def follow(self, deck: Deck, index: int) -> None:
        """Pone `deck` como activa en la diapositiva `index`. Lo usa el seguimiento de PowerPoint."""
        self.add_deck(deck)
        self._active = deck.name
        self._index = index if 1 <= index <= deck.total else 1

    def select(self, name: str) -> None:
        if name not in self._decks:
            raise ProtocolError(tr('presentación no cargada: {0}', f'{name}'))
        self._active = name
        self._index = 1

    def goto(self, index: int) -> None:
        deck = self._active_deck()
        if not 1 <= index <= deck.total:
            raise ProtocolError(tr('índice fuera de rango: {0} (1..{1})', f'{index}', f'{deck.total}'))
        self._index = index

    def next(self) -> None:
        deck = self._active_deck()
        if self._index < deck.total:
            self._index += 1

    def prev(self) -> None:
        if self._index > 1:
            self._index -= 1

    def current_message(self) -> dict:
        if self._active is None:
            return slide_message(None, 0, 0, "")
        deck = self._decks[self._active]
        if deck.total == 0:
            return slide_message(deck.name, 0, 0, "")
        return slide_message(deck.name, self._index, deck.total, deck.notes[self._index - 1])

    def _active_deck(self) -> Deck:
        if self._active is None:
            raise ProtocolError(tr('no hay ninguna presentación activa'))
        return self._decks[self._active]
