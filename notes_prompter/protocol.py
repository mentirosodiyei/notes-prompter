"""Mensajes JSON del protocolo WebSocket. Todos los índices son base 1."""

from __future__ import annotations

from .i18n import tr

import json
from typing import Any

ROLES = frozenset({"display", "control"})
COMMAND_TYPES = frozenset({"hello", "goto", "next", "prev", "load", "select"})


class ProtocolError(ValueError):
    """Mensaje o comando no válido. El texto es apto para mostrar al operador."""


def slide_message(presentation: str | None, index: int, total: int, notes: str) -> dict[str, Any]:
    return {
        "type": "slide",
        "presentation": presentation,
        "index": index,
        "total": total,
        "notes": notes,
    }


def presentations_message(names: list[str], active: str | None) -> dict[str, Any]:
    return {"type": "presentations", "items": names, "active": active}


def error_message(text: str) -> dict[str, Any]:
    return {"type": "error", "message": text}


def parse_command(raw: str) -> dict[str, Any]:
    """Valida un mensaje entrante y lo devuelve como dict. Lanza ProtocolError si no es válido."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(tr('el mensaje no es JSON válido')) from exc
    if not isinstance(data, dict):
        raise ProtocolError(tr('el mensaje debe ser un objeto JSON'))

    kind = data.get("type")
    if kind not in COMMAND_TYPES:
        raise ProtocolError(tr('tipo de mensaje desconocido: {0}', f'{kind!r}'))

    if kind == "hello":
        if data.get("role") not in ROLES:
            raise ProtocolError(tr("'role' debe ser 'display' o 'control'"))
    elif kind == "goto":
        index = data.get("index")
        # bool es subclase de int en Python; lo rechazamos explícitamente.
        if type(index) is not int:
            raise ProtocolError(tr("'index' debe ser un entero"))
    elif kind == "load":
        path = data.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ProtocolError(tr("'path' debe ser una ruta no vacía"))
    elif kind == "select":
        name = data.get("presentation")
        if not isinstance(name, str) or not name:
            raise ProtocolError(tr("'presentation' debe ser un nombre no vacío"))
    return data


def parse_slide(raw: str) -> dict[str, Any]:
    """Valida una diapositiva recibida de otro agente antes de retransmitirla."""
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProtocolError(tr('la diapositiva no es JSON válido')) from exc
    if not isinstance(data, dict) or data.get("type") != "slide":
        raise ProtocolError(tr('se esperaba una diapositiva'))
    name, index, total, notes = (data.get(k) for k in ("presentation", "index", "total", "notes"))
    if type(index) is not int or type(total) is not int or total < 0:
        raise ProtocolError(tr('índices de diapositiva no válidos'))
    if not isinstance(notes, str) or not (name is None or isinstance(name, str) and name):
        raise ProtocolError(tr('nombre o notas no válidos'))
    if total == 0:
        if index != 0 or notes != "":
            raise ProtocolError(tr('una presentación vacía no puede tener notas ni índice'))
    elif name is None or not 1 <= index <= total:
        raise ProtocolError(tr('índice fuera de la presentación'))
    return slide_message(name, index, total, notes)
