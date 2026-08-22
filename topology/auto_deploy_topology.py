#!/usr/bin/env python3
"""
Auto-deploying Hybrid Cloud-SDN topology.
Automatically starts the backend Flask services and iperf servers
right after the network comes up -- no manual per-host commands needed.

Run with:
    sudo python3 topology/auto_deploy_topology.py
"""
import time
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

    h1 = net.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
    h2 = net.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
    h3 = net.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
    h4 = net.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')

    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(h3, s1)
    net.addLink(s1, s2, delay='20ms', bw=10)
    net.addLink(h4, s2)

    net.start()

    print("*** Waiting for controller to finish wiring switches...")
    time.sleep(3)

    print("*** Auto-starting backend services (h2, h3, h4)...")
    h2.cmd('python3 backend/server_app.py --name private-A --port 80 > logs/h2_backend.log 2>&1 &')
    h3.cmd('python3 backend/server_app.py --name private-B --port 80 > logs/h3_backend.log 2>&1 &')
    h4.cmd('python3 backend/server_app.py --name cloud-node --port 80 > logs/h4_backend.log 2>&1 &')

    print("*** Auto-starting iperf servers (h2, h3) for load-spike testing...")
    h2.cmd('iperf -s -p 5001 > logs/h2_iperf.log 2>&1 &')
    h3.cmd('iperf -s -p 5001 > logs/h3_iperf.log 2>&1 &')

    time.sleep(2)
    print("\n*** Hybrid Cloud-SDN testbed is fully deployed and ready.")
    print("*** Virtual service IP: 10.0.0.100")
    print("*** Try:  h1 curl http://10.0.0.100/")
    print("*** Run the demo:  h1 bash testing/demo_cycle.sh")
    print("*** Dashboard: http://localhost:8081/index.html\n")

    CLI(net)
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    build()
