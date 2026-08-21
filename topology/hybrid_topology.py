#!/usr/bin/env python3
"""
Hybrid Cloud-SDN Topology
--------------------------
private segment (s1): h1 (client), h2 & h3 (private servers)
cloud segment  (s2): h4 (cloud server)
s1 <-> s2 link carries a simulated WAN delay/bandwidth cap.

Run with:
    sudo python3 hybrid_topology.py
(Ryu controller must already be running on 127.0.0.1:6633)
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel


def build():
    net = Mininet(controller=RemoteController, switch=OVSSwitch,
                   link=TCLink, autoSetMacs=False)

    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6633)

    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    s2 = net.addSwitch('s2', protocols='OpenFlow13')

    h1 = net.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')  # client
    h2 = net.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')  # private server A
    h3 = net.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')  # private server B
    h4 = net.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')  # cloud server

    # Order matters: this determines the OpenFlow port numbers the
    # controller expects (s1: port1=h1, port2=h2, port3=h3, port4=s2link)
    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(h3, s1)
    net.addLink(s1, s2, delay='20ms', bw=10)   # the simulated on-prem <-> cloud WAN link
    net.addLink(h4, s2)                         # s2: port1=s1link, port2=h4

    net.start()
    print("\n*** Hybrid Cloud-SDN testbed is up.")
    print("*** Virtual service IP clients should target: 10.0.0.100")
    print("*** Try:  h1 curl http://10.0.0.100/   (after starting backend/server_app.py on h2,h3,h4)\n")
    CLI(net)
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    build()
