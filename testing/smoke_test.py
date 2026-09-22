#!/usr/bin/env python3
"""Non-interactive end-to-end validation for Hybrid Cloud-SDN."""
import os
import shlex
import sys
import time

from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController


def main():
    backend_python = shlex.quote(os.environ.get('HYBRID_BACKEND_PYTHON', sys.executable))
    net = Mininet(controller=RemoteController, switch=OVSSwitch,
                  link=TCLink, autoSetMacs=False)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6633)
    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    s2 = net.addSwitch('s2', protocols='OpenFlow13')
    h1 = net.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
    h2 = net.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
    h3 = net.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
    h4 = net.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')
    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(h3, s1)
    net.addLink(s1, s2, delay='20ms', bw=10)
    net.addLink(h4, s2)

    try:
        net.start()
        time.sleep(3)
        h2.cmd(f'{backend_python} backend/server_app.py --name private-gpu-A --port 80 > logs/smoke-h2.log 2>&1 &')
        h3.cmd(f'{backend_python} backend/server_app.py --name private-gpu-B --port 80 > logs/smoke-h3.log 2>&1 &')
        h4.cmd(f'{backend_python} backend/server_app.py --name cloud-gpu-burst --port 80 > logs/smoke-h4.log 2>&1 &')
        time.sleep(2)
        response = h1.cmd('curl -sS --connect-timeout 5 http://10.0.0.100/')
        if 'served_by' not in response:
            raise RuntimeError(f'virtual-IP request failed: {response.strip()}')
        print(response.strip())
    finally:
        net.stop()


if __name__ == '__main__':
    setLogLevel('warning')
    main()
