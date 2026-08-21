#!/usr/bin/env python3
from controller.db import log_event, log_load_sample
import json
import time
from collections import deque
from webob import Response
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, arp, ipv4, tcp
from ryu.lib import hub
from ryu.app.wsgi import ControllerBase, WSGIApplication, route

VIRTUAL_IP = '10.0.0.100'
VIRTUAL_MAC = '00:00:00:00:01:00'

BACKENDS = {
    'h2': {'ip': '10.0.0.2', 'mac': '00:00:00:00:00:02', 'dpid': 1, 'port': 2, 'cloud': False},
    'h3': {'ip': '10.0.0.3', 'mac': '00:00:00:00:00:03', 'dpid': 1, 'port': 3, 'cloud': False},
    'h4': {'ip': '10.0.0.4', 'mac': '00:00:00:00:00:04', 'dpid': 2, 'port': 2, 'cloud': True},
}

S1_TO_S2_PORT = 4
S2_TO_S1_PORT = 1

MONITOR_INTERVAL_SEC = 2
LOAD_THRESHOLD_BYTES_PER_SEC = 5_000
FLOW_IDLE_TIMEOUT = 5
HISTORY_LENGTH = 30
EVENT_LOG_LENGTH = 15


class HybridLBRestController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(HybridLBRestController, self).__init__(req, link, data, **config)
        self.lb_app = data['lb_app']

    @route('hybridlb', '/status', methods=['GET'])
    def status(self, req, **kwargs):
        body = json.dumps(self.lb_app.get_status(), indent=2)
        return Response(content_type='application/json', charset='UTF-8', body=body,
                         headerlist=[('Access-Control-Allow-Origin', '*')])


class HybridCloudLoadBalancer(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(HybridCloudLoadBalancer, self).__init__(*args, **kwargs)
        self.datapaths = {}
        self.mac_to_port = {}
        self._prev_byte_count = {}
        self.port_load = {}
        self.last_decision = None
        self.last_threshold_exceeded = False
        self.spike_started_at = None
        self.history = deque(maxlen=HISTORY_LENGTH)
        self.event_log = deque(maxlen=EVENT_LOG_LENGTH)
        self.monitor_thread = hub.spawn(self._monitor_loop)

        wsgi = kwargs['wsgi']
        wsgi.register(HybridLBRestController, {'lb_app': self})

    def _log_event(self, message):
        self.event_log.appendleft({
            'time': time.strftime('%H:%M:%S'),
            'message': message,
        })

    def get_status(self):
        backends = {}
        for name, b in BACKENDS.items():
            backends[name] = {
                'load_bytes_per_sec': round(self.backend_load(name), 1),
                'is_cloud': b['cloud'],
            }
        spike_duration = None
        if self.spike_started_at is not None:
            spike_duration = round(time.time() - self.spike_started_at, 1)
        return {
            'backends': backends,
            'threshold_bytes_per_sec': LOAD_THRESHOLD_BYTES_PER_SEC,
            'last_decision': self.last_decision,
            'threshold_exceeded': self.last_threshold_exceeded,
            'spike_duration_sec': spike_duration,
            'history': list(self.history),
            'event_log': list(self.event_log),
        }

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
            self.logger.info("Switch connected: dpid=%s", dp.id)
        elif ev.state == DEAD_DISPATCHER:
            self.datapaths.pop(dp.id, None)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self.add_flow(dp, priority=0, match=match, actions=actions)

    def add_flow(self, dp, priority, match, actions, idle_timeout=0):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=dp, priority=priority, match=match,
                                 instructions=inst, idle_timeout=idle_timeout)
        dp.send_msg(mod)

    def _monitor_loop(self):
        while True:
            for dp in list(self.datapaths.values()):
                parser = dp.ofproto_parser
                req = parser.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY)
                dp.send_msg(req)
            hub.sleep(MONITOR_INTERVAL_SEC)
            self.history.append({
                'time': time.strftime('%H:%M:%S'),
                'h2': round(self.backend_load('h2'), 1),
                'h3': round(self.backend_load('h3'), 1),
                'h4': round(self.backend_load('h4'), 1),
            })

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        dpid = ev.msg.datapath.id
        for stat in ev.msg.body:
            key = (dpid, stat.port_no)
            current_total = stat.tx_bytes + stat.rx_bytes
            previous_total = self._prev_byte_count.get(key)
            if previous_total is not None:
                delta = max(0, current_total - previous_total)
                self.port_load[key] = delta / float(MONITOR_INTERVAL_SEC)
            self._prev_byte_count[key] = current_total

    def backend_load(self, name):
        b = BACKENDS[name]
        return self.port_load.get((b['dpid'], b['port']), 0.0)

    def choose_backend(self):
        private_names = [n for n, b in BACKENDS.items() if not b['cloud']]
        loads = {n: self.backend_load(n) for n in private_names}
        best_private = min(loads, key=loads.get)

        if loads[best_private] > LOAD_THRESHOLD_BYTES_PER_SEC:
            cloud_name = next(n for n, b in BACKENDS.items() if b['cloud'])
            self.logger.info(
                "[THRESHOLD EXCEEDED] best private load=%.0f B/s > %.0f B/s -> CLOUD OFFLOAD to %s",
                loads[best_private], LOAD_THRESHOLD_BYTES_PER_SEC, cloud_name)
            if not self.last_threshold_exceeded:
                self.spike_started_at = time.time()
                self._log_event(f"Spike detected ({loads[best_private]:.0f} B/s) — offloading to {cloud_name}")
            self.last_decision = cloud_name
            self.last_threshold_exceeded = True
            return cloud_name

        if self.last_threshold_exceeded:
            self._log_event(f"Load recovered — back to local routing ({best_private})")
        self.spike_started_at = None
        self.logger.info("[LOCAL] routing to %s (load=%.0f B/s)", best_private, loads[best_private])
        self.last_decision = best_private
        self.last_threshold_exceeded = False
        return best_private

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
            reply_eth = ethernet.ethernet(dst=eth.src, src=VIRTUAL_MAC,
                                           ethertype=ether_types.ETH_TYPE_ARP)
            reply_arp = arp.arp(opcode=arp.ARP_REPLY, src_mac=VIRTUAL_MAC, src_ip=VIRTUAL_IP,
                                 dst_mac=arp_pkt.src_mac, dst_ip=arp_pkt.src_ip)
            reply_pkt = packet.Packet()
            reply_pkt.add_protocol(reply_eth)
            reply_pkt.add_protocol(reply_arp)
            reply_pkt.serialize()
            actions = [parser.OFPActionOutput(in_port)]
            out = parser.OFPPacketOut(datapath=dp, buffer_id=ofp.OFP_NO_BUFFER,
                                       in_port=ofp.OFPP_CONTROLLER, actions=actions,
                                       data=reply_pkt.data)
            dp.send_msg(out)
        else:
            self._learning_switch_forward(dp, in_port, eth, msg)

    def _handle_service_request(self, dp, in_port, ip_hdr, tcp_hdr, msg):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        backend_name = self.choose_backend()
        b = BACKENDS[backend_name]
        out_port = self._out_port_toward(dp.id, b)

        fwd_match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ip_proto=6,
                                     ipv4_dst=VIRTUAL_IP, in_port=in_port,
                                     tcp_src=tcp_hdr.src_port, tcp_dst=tcp_hdr.dst_port)
        fwd_actions = [
            parser.OFPActionSetField(eth_dst=b['mac']),
            parser.OFPActionSetField(ipv4_dst=b['ip']),
            parser.OFPActionOutput(out_port),
        ]
        self.add_flow(dp, priority=10, match=fwd_match, actions=fwd_actions,
                       idle_timeout=FLOW_IDLE_TIMEOUT)

        rev_match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ip_proto=6,
                                     ipv4_src=b['ip'], ipv4_dst=ip_hdr.src,
                                     tcp_src=tcp_hdr.dst_port, tcp_dst=tcp_hdr.src_port)
        rev_actions = [
            parser.OFPActionSetField(eth_src=VIRTUAL_MAC),
            parser.OFPActionSetField(ipv4_src=VIRTUAL_IP),
            parser.OFPActionOutput(in_port),
        ]
        self.add_flow(dp, priority=10, match=rev_match, actions=rev_actions,
                       idle_timeout=FLOW_IDLE_TIMEOUT)

        out = parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id,
                                   in_port=in_port, actions=fwd_actions, data=msg.data)
        dp.send_msg(out)

    def _out_port_toward(self, dpid, backend):
        if backend['dpid'] == dpid:
            return backend['port']
        return S1_TO_S2_PORT if dpid == 1 else S2_TO_S1_PORT

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
