#!/usr/bin/env python3
"""
STATIC ROUTING BASELINE CONTROLLER — for benchmark comparison only.

Mimics traditional static routing (like OSPF picking one path once):
ALWAYS sends every request to h2, regardless of load, with no
monitoring and no offload. Used to generate a real, measured
"static baseline" comparison against the dynamic controller.

Run with:
    ryu-manager controller/static_baseline_controller.py --wsapi-port 8081
"""
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, arp, ipv4, tcp

VIRTUAL_IP = '10.0.0.100'
VIRTUAL_MAC = '00:00:00:00:01:00'

FIXED_BACKEND = {'ip': '10.0.0.2', 'mac': '00:00:00:00:00:02', 'dpid': 1, 'port': 2}


class StaticBaselineController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(StaticBaselineController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self.add_flow(dp, 0, match, actions)

    def add_flow(self, dp, priority, match, actions, idle_timeout=0):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=dp, priority=priority, match=match,
                                 instructions=inst, idle_timeout=idle_timeout)
        dp.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return

        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            self._handle_arp(dp, in_port, pkt, msg)
            return

        if eth.ethertype == ether_types.ETH_TYPE_IP:
            ip_hdr = pkt.get_protocol(ipv4.ipv4)
            tcp_hdr = pkt.get_protocol(tcp.tcp)
            if ip_hdr and ip_hdr.dst == VIRTUAL_IP and tcp_hdr:
                self._handle_service_request(dp, in_port, ip_hdr, tcp_hdr, msg)
                return

        self._learning_switch_forward(dp, in_port, eth, msg)

    def _handle_arp(self, dp, in_port, pkt, msg):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        arp_pkt = pkt.get_protocol(arp.arp)
        eth = pkt.get_protocol(ethernet.ethernet)
        if arp_pkt and arp_pkt.dst_ip == VIRTUAL_IP and arp_pkt.opcode == arp.ARP_REQUEST:
            reply_eth = ethernet.ethernet(dst=eth.src, src=VIRTUAL_MAC, ethertype=ether_types.ETH_TYPE_ARP)
            reply_arp = arp.arp(opcode=arp.ARP_REPLY, src_mac=VIRTUAL_MAC, src_ip=VIRTUAL_IP,
                                 dst_mac=arp_pkt.src_mac, dst_ip=arp_pkt.src_ip)
            reply_pkt = packet.Packet()
            reply_pkt.add_protocol(reply_eth)
            reply_pkt.add_protocol(reply_arp)
            reply_pkt.serialize()
            actions = [parser.OFPActionOutput(in_port)]
            out = parser.OFPPacketOut(datapath=dp, buffer_id=ofp.OFP_NO_BUFFER,
                                       in_port=ofp.OFPP_CONTROLLER, actions=actions, data=reply_pkt.data)
            dp.send_msg(out)
        else:
            self._learning_switch_forward(dp, in_port, eth, msg)

    def _handle_service_request(self, dp, in_port, ip_hdr, tcp_hdr, msg):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        b = FIXED_BACKEND
        self.logger.info("[STATIC] routing to fixed backend h2 (no load check)")

        fwd_match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ip_proto=6,
                                     ipv4_dst=VIRTUAL_IP, in_port=in_port,
                                     tcp_src=tcp_hdr.src_port, tcp_dst=tcp_hdr.dst_port)
        fwd_actions = [
            parser.OFPActionSetField(eth_dst=b['mac']),
            parser.OFPActionSetField(ipv4_dst=b['ip']),
            parser.OFPActionOutput(b['port']),
        ]
        self.add_flow(dp, 10, fwd_match, fwd_actions, idle_timeout=5)

        rev_match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ip_proto=6,
                                     ipv4_src=b['ip'], ipv4_dst=ip_hdr.src,
                                     tcp_src=tcp_hdr.dst_port, tcp_dst=tcp_hdr.src_port)
        rev_actions = [
            parser.OFPActionSetField(eth_src=VIRTUAL_MAC),
            parser.OFPActionSetField(ipv4_src=VIRTUAL_IP),
            parser.OFPActionOutput(in_port),
        ]
        self.add_flow(dp, 10, rev_match, rev_actions, idle_timeout=5)

        out = parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id,
                                   in_port=in_port, actions=fwd_actions, data=msg.data)
        dp.send_msg(out)

    def _learning_switch_forward(self, dp, in_port, eth, msg):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        dpid = dp.id
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][eth.src] = in_port
        out_port = self.mac_to_port[dpid].get(eth.dst, ofp.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]
        out = parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id,
                                   in_port=in_port, actions=actions, data=msg.data)
        dp.send_msg(out)
