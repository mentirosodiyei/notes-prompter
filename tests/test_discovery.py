from __future__ import annotations

import json
import socket
import time

from notes_prompter.discovery import (
    PeerListener,
    decode_announcement,
    encode_announcement,
)
from notes_prompter.screens import kiosk_command, Screen


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_announcement_round_trip():
    data = encode_announcement("PC-PONENTE", 8765, "charla")
    assert decode_announcement(data) == {
        "app": "notes-prompter",
        "name": "PC-PONENTE",
        "port": 8765,
        "presentation": "charla",
    }


def test_decode_rejects_foreign_or_broken_packets():
    assert decode_announcement(b"no es json") is None
    assert decode_announcement(b"[1]") is None
    assert decode_announcement(json.dumps({"app": "otra", "name": "x", "port": 1, "presentation": ""}).encode()) is None
    assert decode_announcement(json.dumps({"app": "notes-prompter", "name": "x", "port": "1", "presentation": ""}).encode()) is None
    assert decode_announcement(json.dumps({"app": "notes-prompter", "name": "x", "port": 70000, "presentation": ""}).encode()) is None


def test_listener_collects_peer_and_keeps_ip_and_port():
    port = free_udp_port()
    listener = PeerListener(discovery_port=port)
    listener.start()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(encode_announcement("PC-A", 8765, "charla"), ("127.0.0.1", port))
            deadline = time.monotonic() + 3
            while not listener.peers() and time.monotonic() < deadline:
                time.sleep(0.05)
        peers = listener.peers()
        assert len(peers) == 1
        assert (peers[0].ip, peers[0].port, peers[0].name, peers[0].presentation) == (
            "127.0.0.1", 8765, "PC-A", "charla"
        )
        assert peers[0].url == "http://127.0.0.1:8765/display"
        assert peers[0].label == "PC-A · charla (127.0.0.1)"
    finally:
        listener.stop()


def test_peer_without_presentation_has_clear_label():
    port = free_udp_port()
    listener = PeerListener(discovery_port=port)
    listener.start()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(encode_announcement("PC-B", 8765, ""), ("127.0.0.1", port))
            deadline = time.monotonic() + 3
            while not listener.peers() and time.monotonic() < deadline:
                time.sleep(0.05)
        assert listener.peers()[0].label == "PC-B · sin presentación (127.0.0.1)"
    finally:
        listener.stop()


def test_kiosk_command_places_window_on_selected_screen():
    screen = Screen(index=1, x=1920, y=0, width=1920, height=1080)
    cmd = kiosk_command("/bin/chrome", "http://10.0.0.5:8765/display", screen, "/tmp/perfil")
    assert cmd == [
        "/bin/chrome",
        "--kiosk",
        "--no-first-run",
        "--user-data-dir=/tmp/perfil",
        "--window-position=1920,0",
        "http://10.0.0.5:8765/display",
    ]


def test_kiosk_command_without_screen_omits_position():
    cmd = kiosk_command("/bin/chrome", "http://x/display", None, "/tmp/p")
    assert not any(arg.startswith("--window-position") for arg in cmd)
    assert cmd[-1] == "http://x/display"


def test_edge_kiosk_uses_fullscreen_mode_and_negative_position():
    screen = Screen(index=1, x=-1920, y=0, width=1920, height=1080)
    cmd = kiosk_command("msedge.exe", "http://127.0.0.1:8765/display", screen, "perfil aislado")
    assert "--edge-kiosk-type=fullscreen" in cmd
    assert "--window-position=-1920,0" in cmd
    assert "--user-data-dir=perfil aislado" in cmd
