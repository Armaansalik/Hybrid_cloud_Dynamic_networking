#!/usr/bin/env python3
"""
Auto-deploying Hybrid Private-GPU + Cloud-GPU Inference Routing Topology.

Framing: h2/h3 represent on-premises GPU inference nodes (VLAN 10),
h4 represents a cloud-burst GPU inference node (VLAN 20). The SDN
controller dynamically routes inference requests between them based
on live GPU/node load, exactly as hybrid AI infrastructure does today
to control cloud GPU cost while preserving response time.

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

    s1 = net.addSwitch('s1', protocols='OpenFlow13')  # private GPU segment switch
    s2 = net.addSwitch('s2', protocols='OpenFlow13')  # cloud-burst segment switch

    h1 = net.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')  # client / API caller
    h2 = net.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')  # private GPU node A
    h3 = net.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')  # private GPU node B
    h4 = net.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')  # cloud-burst GPU node

    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(h3, s1)
    net.addLink(s1, s2, delay='20ms', bw=10)   # inter-switch trunk link
    net.addLink(h4, s2)

    net.start()

    print("*** Waiting for controller to finish wiring switches...")
    time.sleep(3)

    print("*** Applying VLAN segmentation: VLAN 10 (private GPU segment), VLAN 20 (cloud-burst segment)")
    # Tag h2 and h3's access ports on s1 into VLAN 10 (private GPU segment)
    s1.cmd('ovs-vsctl set port s1-eth2 tag=10')   # h2
    s1.cmd('ovs-vsctl set port s1-eth3 tag=10')   # h3
    # Tag h4's access port on s2 into VLAN 20 (cloud-burst segment)
    s2.cmd('ovs-vsctl set port s2-eth2 tag=20')   # h4
    # s1<->s2 inter-switch link is left untagged (acts as a trunk carrying both VLANs)
    print("*** VLAN tags applied: h2/h3 -> VLAN 10, h4 -> VLAN 20")

    print("*** Auto-starting GPU inference node services (h2, h3, h4)...")
    h2.cmd('python3 backend/server_app.py --name private-gpu-A --port 80 > logs/h2_backend.log 2>&1 &')
    h3.cmd('python3 backend/server_app.py --name private-gpu-B --port 80 > logs/h3_backend.log 2>&1 &')
    h4.cmd('python3 backend/server_app.py --name cloud-gpu-burst --port 80 > logs/h4_backend.log 2>&1 &')

    print("*** Auto-starting iperf servers (h2, h3) for load-spike testing...")
    h2.cmd('iperf -s -p 5001 > logs/h2_iperf.log 2>&1 &')
    h3.cmd('iperf -s -p 5001 > logs/h3_iperf.log 2>&1 &')

    time.sleep(2)
    print("\n*** Hybrid Private-GPU + Cloud-GPU inference testbed is fully deployed.")
    print("*** AI inference gateway (virtual IP): 10.0.0.100")
    print("*** Try:  h1 curl http://10.0.0.100/")
    print("*** Run the demo:  h1 bash testing/demo_cycle.sh")
    print("*** Dashboard: http://localhost:8081/index.html")
    print("*** VLAN 10 = private GPU nodes (h2, h3) | VLAN 20 = cloud-burst GPU node (h4)\n")

    CLI(net)
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    build()
