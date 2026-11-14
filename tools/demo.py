"""Local, synthetic demo for documentation. Never reads PowerPoint or user settings."""
from __future__ import annotations
import argparse
import asyncio
from contextlib import nullcontext
import signal
import socket
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from notes_prompter import i18n
from notes_prompter.discovery import Peer
from notes_prompter.notes import Deck
from notes_prompter.powerpoint import SlideState
from notes_prompter.server import create_app
from notes_prompter.settings import SettingsStore,PresetInput,DisplaySettings

class DemoWatcher:
    def poll(self):
        text=('Welcome to the conference.\n\nTake a breath and look at the audience.\n\n'
              'Introduce the next section. Keep the pace steady.\n\n')*18
        return SlideState(Deck('Conference demo','demo.pptx',(text,'Explain the next idea.','Thank the audience.')),1)
    def close(self):pass

async def run(port):
    store=SettingsStore()
    preset=store.create_preset('Conference · Rehearsal')
    defaults=DisplaySettings(font_mode='fixed',min_font_px=52,speed_px_s=24,start_delay_s=0)
    store.replace_preset(preset.id,PresetInput(name=preset.name,presentation='Conference demo',presentation_total=3,
        defaults=defaults,rules={1:defaults,2:DisplaySettings(font_mode='fixed',min_font_px=64,speed_px_s=18),
                              3:DisplaySettings(font_mode='fixed',min_font_px=72,speed_px_s=0)}))
    peers=lambda:[Peer('127.0.0.1',port+1,'Demo stage','Conference demo')]
    apps=[create_app(upstream=f'ws://127.0.0.1:{port+1}/ws',peers_fn=peers,allow_local_source=False,settings=store),
          create_app(powerpoint=DemoWatcher(),role='agent',poll_interval=.1)]
    servers=[];sockets=[]
    try:
        for offset,app in enumerate(apps):
            sock=socket.socket();sock.bind(('127.0.0.1',port+offset));sockets.append(sock)
            server=uvicorn.Server(uvicorn.Config(app,log_level='error'));server.capture_signals=nullcontext;servers.append(server)
        stop=asyncio.Event();loop=asyncio.get_running_loop()
        for sig in (signal.SIGINT,signal.SIGTERM):
            try:loop.add_signal_handler(sig,stop.set)
            except NotImplementedError:pass
        tasks=[asyncio.create_task(server.serve(sockets=[sock])) for server,sock in zip(servers,sockets)]
        await stop.wait()
        for server in servers:server.should_exit=True
        await asyncio.gather(*tasks)
    finally:
        for sock in sockets:sock.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=9000)
    parser.add_argument('--language',choices=['en','ca','es'])
    args=parser.parse_args()
    if args.language:i18n.get_language=lambda:args.language
    with patch('notes_prompter.server.socket.gethostname',return_value='Demo receiver'):
        asyncio.run(run(args.port))
