import sys
import threading
import time
from types import SimpleNamespace

from notes_prompter.tray import TrayService


class Menu:
    SEPARATOR=object()
    def __init__(self,*items):
        self.items=items


class Item:
    def __init__(self,text,action,**kwargs):
        self.text=text
        self.action=action
        self.enabled=kwargs.get('enabled', True)


class Icon:
    def __init__(self,name,image,title,menu):
        self.menu=menu
        self.visible=False
        self.done=threading.Event()
    def run(self):
        self.visible=True
        self.done.wait(5)
        self.visible=False
    def stop(self):
        self.done.set()
    def update_menu(self):
        pass


def test_tray_actions_are_queued_for_the_tk_thread(monkeypatch):
    monkeypatch.setattr(sys,'platform','win32')
    monkeypatch.setitem(sys.modules,'pystray',SimpleNamespace(Icon=Icon,Menu=Menu,MenuItem=Item))
    service=TrayService()
    service.start()
    deadline=time.monotonic()+2
    while not service.available and time.monotonic()<deadline:
        time.sleep(.01)
    assert service.available
    for item in service.icon.menu.items:
        if isinstance(item,Item):
            item.action()
    assert [service.actions.get_nowait() for _ in range(3)]==['open','admin','exit']
    service.stop()
    assert not service.available
    assert not service.thread.is_alive()


def test_failed_tray_backend_does_not_leave_a_visible_icon(monkeypatch):
    class FailingIcon(Icon):
        def run(self):
            raise OSError('Windows ha bloqueado el icono')
    monkeypatch.setattr(sys,'platform','win32')
    monkeypatch.setitem(sys.modules,'pystray',SimpleNamespace(Icon=FailingIcon,Menu=Menu,MenuItem=Item))
    service=TrayService()
    service.start()
    service.thread.join(2)
    assert not service.available
    assert service.error
    service.stop()


def test_tray_configuration_access_follows_desktop_role(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setitem(sys.modules, 'pystray', SimpleNamespace(Icon=Icon, Menu=Menu, MenuItem=Item))
    service = TrayService()
    service.set_configuration_enabled(False)
    service.start()
    try:
        panel = next(item for item in service.icon.menu.items if isinstance(item, Item) and item.text == 'Panel de administración')
        assert panel.enabled(None) is False
        service.set_configuration_enabled(True)
        assert panel.enabled(None) is True
    finally:
        service.stop()
