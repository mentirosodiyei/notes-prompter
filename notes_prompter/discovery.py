"""Descubrimiento de agentes en la LAN por UDP broadcast."""

from __future__ import annotations

from .i18n import tr

import json
import socket
import threading
import time
from dataclasses import dataclass

from .network import send_announcement

DISCOVERY_PORT = 8766
ANNOUNCE_INTERVAL = 2.0
PEER_TTL = 6.0  # segundos sin anuncio para dar un agente por desaparecido
MAGIC = "notes-prompter"


def encode_announcement(name: str, http_port: int, presentation: str) -> bytes:
    return json.dumps(
        {"app": MAGIC, "name": name, "port": http_port, "presentation": presentation}
    ).encode("utf-8")


def decode_announcement(data: bytes) -> dict | None:
    """Devuelve el anuncio si es de notes-prompter y está bien formado; si no, None."""
    try:
        msg = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(msg, dict) or msg.get("app") != MAGIC:
        return None
    port = msg.get("port")
    if type(port) is not int or not 0 < port < 65536:
        return None
    if not isinstance(msg.get("name"), str) or not isinstance(msg.get("presentation"), str):
        return None
    return msg


@dataclass(frozen=True)
class Peer:
    ip: str
    port: int
    name: str
    presentation: str

    @property
    def url(self) -> str:
        return f"http://{self.ip}:{self.port}/display"

    @property
    def label(self) -> str:
        shown = self.presentation or tr('sin presentación')
        return f"{self.name} · {shown} ({self.ip})"


class Announcer(threading.Thread):
    """Anuncia periódicamente este agente. `presentation_fn` devuelve la presentación activa."""

    def __init__(
        self,
        name: str,
        http_port: int,
        presentation_fn,
        discovery_port: int = DISCOVERY_PORT,
        interval: float = ANNOUNCE_INTERVAL,
    ) -> None:
        super().__init__(daemon=True)
        self._name = name
        self._http_port = http_port
        self._presentation_fn = presentation_fn
        self._discovery_port = discovery_port
        self._interval = interval
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            payload = encode_announcement(self._name, self._http_port, self._presentation_fn() or "")
            send_announcement(payload, self._discovery_port)
            self._stop_event.wait(self._interval)

    def stop(self) -> None:
        self._stop_event.set()


class PeerListener(threading.Thread):
    """Escucha anuncios y mantiene la lista de agentes vistos recientemente."""

    def __init__(self, discovery_port: int = DISCOVERY_PORT) -> None:
        super().__init__(daemon=True)
        self._discovery_port = discovery_port
        self._peers: dict[tuple[str, int], tuple[Peer, float]] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        # Se enlaza aquí, no en el hilo, para que el puerto esté escuchando al volver del constructor.
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("", self._discovery_port))
        self._sock.settimeout(0.5)

    def run(self) -> None:
        sock = self._sock
        while not self._stop_event.is_set():
            try:
                data, (ip, _) = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break  # socket cerrado al parar
            msg = decode_announcement(data)
            if msg is None:
                continue
            peer = Peer(ip=ip, port=msg["port"], name=msg["name"], presentation=msg["presentation"])
            with self._lock:
                self._peers[(ip, peer.port)] = (peer, time.monotonic())
        sock.close()

    def peers(self) -> list[Peer]:
        now = time.monotonic()
        with self._lock:
            alive = [peer for peer, seen in self._peers.values() if now - seen <= PEER_TTL]
        return sorted(alive, key=lambda p: (p.name, p.ip, p.port))

    def stop(self) -> None:
        self._stop_event.set()
        if self._sock is not None:
            self._sock.close()
