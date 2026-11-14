"""Two notes-only agents and a receiver master, all synthetic and loopback-only."""
import asyncio
import json
from pathlib import Path
import socket
import sys
import uvicorn
sys.path.insert(0, sys.argv[1])
from notes_prompter.discovery import Peer
from notes_prompter.notes import Deck
from notes_prompter.powerpoint import SlideState
from notes_prompter.server import create_app
from notes_prompter.settings import PresetInput, SettingsStore
from notes_prompter.state import Controller

class FakePowerPoint:
    index = 1
    error = None
    deck = Deck('Ensayo local', 'synthetic-local.pptx', ('Nota de prueba uno', 'Nota de prueba dos', 'Nota tres'))
    def poll(self): return SlideState(self.deck, self.index)
    def close(self): pass

def local_socket():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    return sock

async def main():
    store = SettingsStore(Path(sys.argv[2]))
    preset = store.create_preset('Ensayo de Companion')
    store.replace_preset(preset.id, PresetInput(name=preset.name, presentation='Ensayo local'))
    watcher = FakePowerPoint()
    first_app = create_app(powerpoint=watcher, role='agent', poll_interval=.02)
    first_sock = local_socket(); first_port = first_sock.getsockname()[1]
    remote_ctrl = Controller()
    remote_ctrl.add_deck(Deck('Ensayo remoto', 'synthetic-remote.pptx', ('Remota uno', 'Remota dos')))
    remote_app = create_app(remote_ctrl, role='agent')
    remote_sock = local_socket(); remote_port = remote_sock.getsockname()[1]
    first_peer = Peer('127.0.0.1', first_port, 'PC A de prueba', 'Ensayo local')
    remote_peer = Peer('127.0.0.1', remote_port, 'PC B de prueba', 'Ensayo remoto')
    peers = [first_peer, remote_peer]
    app = create_app(upstream=f'ws://127.0.0.1:{first_port}/ws', peers_fn=lambda: peers,
                     settings=store, allow_local_source=False)
    @app.put('/_fixture/slide/{index}')
    async def fixture_slide(index: int):
        watcher.index = index; remote_ctrl.goto(index)
        return {'index': index}
    @app.put('/_fixture/peers/{visible}')
    async def fixture_peers(visible: int):
        peers[:] = [first_peer, remote_peer] if visible else [first_peer]
        return {'visible': visible}
    master_sock = local_socket()
    servers = [uvicorn.Server(uvicorn.Config(app, log_level='error', ws='websockets')) for app in [app, first_app, remote_app]]
    tasks = [asyncio.create_task(server.serve(sockets=[sock])) for server, sock in zip(servers, [master_sock, first_sock, remote_sock])]
    while not all(server.started for server in servers): await asyncio.sleep(.01)
    print(json.dumps({'master_port': master_sock.getsockname()[1], 'remote_port': remote_port, 'first_agent_port': first_port}), flush=True)
    await asyncio.gather(*tasks)
asyncio.run(main())
