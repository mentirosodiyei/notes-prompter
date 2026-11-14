import socket
from types import SimpleNamespace

from notes_prompter import network


def test_multiple_lans_ignore_down_loopback_and_point_to_point(monkeypatch):
    def addr(ip,broadcast=None):
        return SimpleNamespace(family=socket.AF_INET,address=ip,broadcast=broadcast)
    addresses={'lo':[addr('127.0.0.1','127.255.255.255')],
               'wifi':[addr('10.0.0.2','10.0.0.255')],
               'ethernet':[addr('192.0.2.102','192.0.2.255')],
               'vpn':[addr('10.192.1.8')],
               'down':[addr('172.16.0.2','172.16.0.255')]}
    monkeypatch.setattr(network.psutil,'net_if_addrs',lambda:addresses)
    monkeypatch.setattr(network.psutil,'net_if_stats',lambda:{k:SimpleNamespace(isup=k!='down') for k in addresses})
    assert network.lan_interfaces()==[network.LanInterface('10.0.0.2','10.0.0.255'),network.LanInterface('192.0.2.102','192.0.2.255')]
    assert {'127.0.0.1','10.0.0.2','192.0.2.102','10.192.1.8'} <= network.local_addresses()


def test_broadcasts_bind_each_interface_and_survive_one_failure(monkeypatch):
    monkeypatch.setattr(network,'lan_interfaces',lambda:[network.LanInterface('10.0.0.2','10.0.0.255'),network.LanInterface('192.0.2.102','192.0.2.255')])
    events=[]
    class Sock:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def setsockopt(self,*a):pass
        def bind(self,address):
            self.address=address
        def sendto(self,payload,target):
            events.append((self.address,payload,target))
            if self.address[0]=='10.0.0.2':raise OSError('unavailable')
    monkeypatch.setattr(network.socket,'socket',lambda *a:Sock())
    network.send_announcement(b'notes',8766)
    assert events==[(('10.0.0.2',0),b'notes',('10.0.0.255',8766)),(('192.0.2.102',0),b'notes',('192.0.2.255',8766))]


def test_lan_address_does_not_advertise_vpn_as_only_lan(monkeypatch):
    from notes_prompter.__main__ import lan_address
    monkeypatch.setattr(network,'lan_interfaces',lambda:[network.LanInterface('192.0.2.102','192.0.2.255')])
    assert lan_address()=='192.0.2.102'


def test_windows_derives_each_lan_broadcast_when_psutil_omits_it(monkeypatch):
    monkeypatch.setattr(network.sys, 'platform', 'win32')
    def addr(ip, mask):
        return SimpleNamespace(family=socket.AF_INET, address=ip, netmask=mask, broadcast=None, ptp=None)
    addresses = {
        'ethernet': [addr('192.168.20.5', '255.255.255.0')],
        'wifi': [addr('10.20.9.3', '255.255.252.0')],
        'vpn': [addr('10.99.0.1', '255.255.255.255')],
        'point-to-point': [addr('10.99.0.2', '255.255.255.254')],
        'invalid': [addr('192.168.1.3', None)],
        'down': [addr('172.16.1.3', '255.255.0.0')],
        'loopback': [addr('127.0.0.1', '255.0.0.0')],
    }
    monkeypatch.setattr(network.psutil, 'net_if_addrs', lambda: addresses)
    monkeypatch.setattr(network.psutil, 'net_if_stats', lambda: {
        name: SimpleNamespace(isup=name != 'down') for name in addresses})
    assert network.lan_interfaces() == [
        network.LanInterface('192.168.20.5', '192.168.20.255'),
        network.LanInterface('10.20.9.3', '10.20.11.255'),
    ]
    assert '10.99.0.1' in network.local_addresses()


def test_unix_point_to_point_without_broadcast_stays_excluded(monkeypatch):
    monkeypatch.setattr(network.sys, 'platform', 'darwin')
    monkeypatch.setattr(network.psutil, 'net_if_addrs', lambda: {
        'vpn': [SimpleNamespace(family=socket.AF_INET, address='10.0.0.2',
            netmask='255.255.255.0', broadcast=None, ptp='10.0.0.1')]})
    monkeypatch.setattr(network.psutil, 'net_if_stats', lambda: {'vpn': SimpleNamespace(isup=True)})
    assert network.lan_interfaces() == []
