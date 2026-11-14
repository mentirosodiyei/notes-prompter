"""Local IPv4 interfaces, including machines with Ethernet, Wi-Fi and a VPN."""
from __future__ import annotations

import socket
import sys
from ipaddress import IPv4Interface
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class LanInterface:
    address: str
    broadcast: str


def local_addresses() -> set[str]:
    return {"127.0.0.1"} | {item.address for items in psutil.net_if_addrs().values()
                           for item in items if item.family == socket.AF_INET}


def lan_interfaces() -> list[LanInterface]:
    active = psutil.net_if_stats()
    found = []
    for name, addresses in psutil.net_if_addrs().items():
        if name not in active or not active[name].isup:
            continue
        for item in addresses:
            if item.family != socket.AF_INET or item.address.startswith("127.") or getattr(item, "ptp", None):
                continue
            broadcast = item.broadcast
            if not broadcast and sys.platform == "win32":
                # Windows may expose only address/netmask, even for an active LAN.
                # Do not fall back to a route selected by a VPN default gateway.
                try:
                    interface = IPv4Interface(f"{item.address}/{item.netmask}")
                except (ValueError, AttributeError):
                    continue
                if interface.network.prefixlen >= 31:
                    continue  # host and point-to-point networks have no broadcast
                broadcast = str(interface.network.broadcast_address)
            if not broadcast:
                continue
            pair = LanInterface(item.address, broadcast)
            if pair not in found:
                found.append(pair)
    return found


def send_announcement(payload: bytes, port: int):
    # A separate bound socket selects the source interface even with a VPN default route.
    interfaces = lan_interfaces()
    targets = [(item.address, item.broadcast) for item in interfaces] or [("0.0.0.0", "255.255.255.255")]
    for address, broadcast in targets:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.bind((address, 0))
                sock.sendto(payload, (broadcast, port))
        except OSError:
            # An unplugged/blocked interface must not prevent announcing on the others.
            continue
