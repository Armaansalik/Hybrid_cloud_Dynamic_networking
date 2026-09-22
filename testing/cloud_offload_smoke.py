#!/usr/bin/env python3
"""Validate that real private-side load causes cloud offload."""
import json
import os
import shlex
import sys
import time
from urllib.request import urlopen

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
        h2.cmd(f'{backend_python} backend/server_app.py --name private-gpu-A --port 80 > logs/cloud-h2.log 2>&1 &')
        h3.cmd(f'{backend_python} backend/server_app.py --name private-gpu-B --port 80 > logs/cloud-h3.log 2>&1 &')
        h4.cmd(f'{backend_python} backend/server_app.py --name cloud-gpu-burst --port 80 > logs/cloud-h4.log 2>&1 &')
        h2.cmd('iperf -s -p 5001 > logs/cloud-h2-iperf.log 2>&1 &')
        h3.cmd('iperf -s -p 5001 > logs/cloud-h3-iperf.log 2>&1 &')
        time.sleep(2)
        h1.cmd('iperf -c 10.0.0.2 -p 5001 -t 9 > /dev/null 2>&1 &')
        h1.cmd('iperf -c 10.0.0.3 -p 5001 -t 9 > /dev/null 2>&1 &')
        time.sleep(5)
        response = h1.cmd('curl -sS --connect-timeout 5 http://10.0.0.100/')
        if 'cloud-gpu-burst' not in response:
            raise RuntimeError(f'cloud offload did not occur: {response.strip()}')
        status = json.load(urlopen('http://127.0.0.1:8082/status', timeout=3))
        if status['last_decision'] != 'h4':
            raise RuntimeError(f'controller status did not record cloud routing: {status}')
        print(response.strip())
        print(json.dumps({'last_decision': status['last_decision'],
                          'offload_probability_pct': status['offload_probability_pct']}))
    finally:
        net.stop()


if __name__ == '__main__':
    setLogLevel('warning')
    main()
