from __future__ import annotations

import json

import pytest

from notes_prompter.protocol import (
    ProtocolError,
    error_message,
    parse_command,
    presentations_message,
    slide_message,
)


def test_slide_message_shape():
    assert slide_message("charla", 3, 12, "texto") == {
        "type": "slide",
        "presentation": "charla",
        "index": 3,
        "total": 12,
        "notes": "texto",
    }


def test_presentations_and_error_messages():
    assert presentations_message(["a", "b"], "a") == {
        "type": "presentations",
        "items": ["a", "b"],
        "active": "a",
    }
    assert error_message("x") == {"type": "error", "message": "x"}


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "hello", "role": "display"},
        {"type": "hello", "role": "control"},
        {"type": "goto", "index": 3},
        {"type": "next"},
        {"type": "prev"},
        {"type": "load", "path": "/tmp/x.pptx"},
        {"type": "select", "presentation": "charla"},
    ],
)
def test_valid_commands_round_trip(payload):
    assert parse_command(json.dumps(payload)) == payload


@pytest.mark.parametrize(
    "raw, fragment",
    [
        ("no es json", "JSON"),
        ("[1, 2]", "objeto"),
        ('{"type": "explode"}', "desconocido"),
        ('{"noType": 1}', "desconocido"),
        ('{"type": "hello", "role": "admin"}', "role"),
        ('{"type": "hello"}', "role"),
        ('{"type": "goto", "index": "3"}', "entero"),
        ('{"type": "goto", "index": 2.5}', "entero"),
        ('{"type": "goto", "index": true}', "entero"),
        ('{"type": "goto"}', "entero"),
        ('{"type": "load", "path": "   "}', "path"),
        ('{"type": "load", "path": 7}', "path"),
        ('{"type": "select", "presentation": ""}', "presentation"),
    ],
)
def test_invalid_messages_raise(raw, fragment):
    with pytest.raises(ProtocolError, match=fragment):
        parse_command(raw)
