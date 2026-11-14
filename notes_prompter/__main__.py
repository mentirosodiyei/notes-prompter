"""Punto de entrada: ``python -m notes_prompter`` o el comando ``notes-prompter``."""

from __future__ import annotations

from .i18n import tr

import argparse
import socket

import uvicorn

from .server import create_app
from .state import Controller


def lan_address() -> str:
    """IP de la interfaz LAN principal. UDP connect no envía paquetes."""
    from .network import lan_interfaces
    interfaces = lan_interfaces()
    if interfaces:
        return interfaces[0].address
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="notes-prompter",
        add_help=False,
        usage="%(prog)s [--help] [--host HOST] [--local] [--port PORT] [--load PATH.pptx]",
        description=tr('Muestra las notas del orador de un .pptx en una pantalla extendida.'),
    )
    parser._optionals.title = tr('opciones')
    parser.add_argument("-h", "--help", action="help", help=tr('muestra esta ayuda y termina'))
    parser.add_argument("--host", default="0.0.0.0", help=tr('interfaz de escucha (por defecto, toda la LAN)'))
    parser.add_argument(
        "--local",
        action="store_true",
        help=tr('modo local: escucha solo en 127.0.0.1 (emisor y receptor en el mismo PC, sin exponer nada a la red)'),
    )
    parser.add_argument("--port", type=int, default=8765, help=tr('puerto HTTP/WebSocket'))
    parser.add_argument(
        "--load",
        action="append",
        default=[],
        dest="loads",
        metavar="PATH.pptx",
        help=tr('carga una presentación al arrancar (se puede repetir)'),
    )
    args = parser.parse_args(argv)
    host = "127.0.0.1" if args.local else args.host

    controller = Controller()
    for path in args.loads:
        controller.load(path)

    if host == "127.0.0.1":
        print(f"Panel:    http://127.0.0.1:{args.port}/")
        print(tr('Receptor: http://127.0.0.1:{0}/display  (ábrelo en Chrome en modo kiosco)', f'{args.port}'))
    else:
        address = lan_address()
        print(tr('Panel:    http://{0}:{1}/   (en este PC: http://127.0.0.1:{2}/)', f'{address}', f'{args.port}', f'{args.port}'))
        print(tr('Receptor: http://{0}:{1}/display  (ábrelo en Chrome en modo kiosco)', f'{address}', f'{args.port}'))
        if host == "0.0.0.0":
            print(tr('Aviso: escuchando en la red local sin autenticación. No lo expongas fuera de tu LAN.'))

    uvicorn.run(create_app(controller), host=host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
