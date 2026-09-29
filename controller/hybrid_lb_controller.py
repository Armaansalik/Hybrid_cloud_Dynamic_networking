#!/usr/bin/env python3
import json
import time
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import log_event, log_load_sample, recent_events, event_count, sample_count, get_long_history
from reliability import CounterSnapshot, ReliabilityPolicy, TelemetryTracker, load_reliability_config

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

# BACKENDS: two private inference nodes and one cloud-burst inference node.
BACKENDS = {
    'h2': {'ip': '10.0.0.2', 'mac': '00:00:00:00:00:02', 'dpid': 1, 'port': 2,
           'cloud': False, 'label': 'Private GPU Node A'},
    'h3': {'ip': '10.0.0.3', 'mac': '00:00:00:00:00:03', 'dpid': 1, 'port': 3,
           'cloud': False, 'label': 'Private GPU Node B'},
    'h4': {'ip': '10.0.0.4', 'mac': '00:00:00:00:00:04', 'dpid': 2, 'port': 2,
           'cloud': True, 'label': 'Cloud-Burst GPU Node'},
}

S1_TO_S2_PORT = 4
S2_TO_S1_PORT = 1

MONITOR_INTERVAL_SEC = 2
FLOW_IDLE_TIMEOUT = 5
HISTORY_LENGTH = 30
EVENT_LOG_LENGTH = 15
FULL_OFFLOAD_MULTIPLIER = 2.0


class HybridLBRestController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(HybridLBRestController, self).__init__(req, link, data, **config)
        self.lb_app = data['lb_app']

    @route('hybridlb', '/status', methods=['GET'])
    def status(self, req, **kwargs):
        body = json.dumps(self.lb_app.get_status(), indent=2)
        return Response(content_type='application/json', charset='UTF-8', body=body,
                         headerlist=[('Access-Control-Allow-Origin', '*')])

    @route('hybridlb', '/set-threshold', methods=['POST', 'OPTIONS'])
    def set_threshold(self, req, **kwargs):
        if req.method == 'OPTIONS':
            return Response(status=200, headerlist=[
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Methods', 'POST, OPTIONS'),
                ('Access-Control-Allow-Headers', 'Content-Type'),
            ])
        try:
            payload = json.loads(req.body.decode('utf-8'))
            new_threshold = float(payload['threshold'])
            self.lb_app.set_threshold(new_threshold)
            body = json.dumps({'ok': True, 'threshold': new_threshold})
        except Exception as e:
            body = json.dumps({'ok': False, 'error': str(e)})
        return Response(content_type='application/json', charset='UTF-8', body=body,
                         headerlist=[('Access-Control-Allow-Origin', '*')])

    @route('hybridlb', '/history-db', methods=['GET'])
    def history_db(self, req, **kwargs):
        minutes = int(req.GET.get('minutes', 60))
        bucket = int(req.GET.get('bucket', 60))
        data = {
            'history': get_long_history(minutes=minutes, bucket_seconds=bucket),
            'recent_events': recent_events(limit=20),
            'total_events_logged': event_count(),
            'total_samples_logged': sample_count(),
        }
        body = json.dumps(data, indent=2)
        return Response(content_type='application/json', charset='UTF-8', body=body,
                         headerlist=[('Access-Control-Allow-Origin', '*')])

    @route('hybridlb', '/backends', methods=['GET'])
    def backends_info(self, req, **kwargs):
        """Full static metadata about each backend -- IP and label."""
        body = json.dumps(BACKENDS, indent=2)
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
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'reliability.json')
        self.reliability_config = load_reliability_config(config_path)
        self.telemetry_tracker = TelemetryTracker(self.reliability_config.ewma_alpha)
        self.backend_telemetry = {}
        self.reliability_policy = ReliabilityPolicy(self.reliability_config)
        self.last_reliability_reason = 'private capacity available'
        self.last_decision = None
        self.last_threshold_exceeded = False
        self.spike_started_at = None
        self.threshold = self.reliability_config.threshold_bytes_per_sec
        self.last_offload_probability = 0.0
        self.history = deque(maxlen=HISTORY_LENGTH)
        self.event_log = deque(maxlen=EVENT_LOG_LENGTH)
        self.monitor_thread = hub.spawn(self._monitor_loop)

        wsgi = kwargs['wsgi']
        wsgi.register(HybridLBRestController, {'lb_app': self})

    def set_threshold(self, new_value):
        old = self.threshold
        self.reliability_config = self.reliability_config.with_threshold(new_value)
        self.threshold = self.reliability_config.threshold_bytes_per_sec
        self._log_event(f"Threshold changed: {old:.0f} -> {self.threshold:.0f} B/s")
        self.reliability_policy.config = self.reliability_config
        self.logger.info("Threshold updated to %.0f B/s", self.threshold)

    def _log_event(self, message):
        self.event_log.appendleft({'time': time.strftime('%H:%M:%S'), 'message': message})
        log_event(message)

    def get_status(self):
        backends = {}
        for name, b in BACKENDS.items():
            telemetry = self.backend_telemetry.get(name, TelemetryTracker._empty_telemetry(name))
            backends[name] = {
                'load_bytes_per_sec': round(self.backend_load(name), 1),
                'is_cloud': b['cloud'],
                'label': b['label'],
                'ip': b['ip'],
                **telemetry.as_dict(),
            }
        spike_duration = None
        if self.spike_started_at is not None:
            spike_duration = round(time.time() - self.spike_started_at, 1)
        return {
            'backends': backends,
            'threshold_bytes_per_sec': self.threshold,
            'last_decision': self.last_decision,
            'threshold_exceeded': self.last_threshold_exceeded,
            'offload_probability_pct': round(self.last_offload_probability * 100, 1),
            'reliability': {
                'mode': self.reliability_policy.mode,
                'reason': self.last_reliability_reason,
                'activation_count': self.reliability_policy.activation_count,
                'recovery_count': self.reliability_policy.recovery_count,
            },
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
            for name in ('h2', 'h3', 'h4'):
                log_load_sample(name, self.backend_load(name))

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        dpid = ev.msg.datapath.id
        for stat in ev.msg.body:
            key = (dpid, stat.port_no)
            backend_name = next((name for name, backend in BACKENDS.items() if backend['dpid'] == dpid and backend['port'] == stat.port_no), None)
            if backend_name is None:
                continue
            snapshot = CounterSnapshot(stat.tx_bytes + stat.rx_bytes, stat.tx_packets + stat.rx_packets, stat.tx_dropped + stat.rx_dropped, stat.tx_errors + stat.rx_errors)
            telemetry = self.telemetry_tracker.update(backend_name, snapshot, MONITOR_INTERVAL_SEC)
            self.backend_telemetry[backend_name] = telemetry
            self.port_load[key] = telemetry.bytes_per_sec

    def backend_load(self, name):
        b = BACKENDS[name]
        return self.port_load.get((b['dpid'], b['port']), 0.0)

    def choose_backend(self):
        """Choose the backend for a newly arrived virtual-IP TCP flow."""
        private_names = [name for name, backend in BACKENDS.items() if not backend['cloud']]
        private_telemetry = {}
        for name in private_names:
            telemetry = self.backend_telemetry.get(name, TelemetryTracker._empty_telemetry(name))
            private_telemetry[name] = telemetry
        previous_mode = self.reliability_policy.mode
        decision = self.reliability_policy.evaluate(private_telemetry, random.random())
        self.last_offload_probability = decision.offload_probability
        self.last_reliability_reason = decision.reason
        self.last_decision = decision.backend
        self.last_threshold_exceeded = decision.mode == 'offloading'
        if previous_mode == 'local' and decision.mode == 'offloading':
            self.spike_started_at = time.time()
            self._log_event('Cloud offload activated: ' + decision.reason)
        elif previous_mode == 'offloading' and decision.mode == 'local':
            self.spike_started_at = None
            self._log_event('Private routing recovered: ' + decision.reason)
        self.logger.info(
            '[ROUTING] %s -> %s (%s, %.0f%% cloud probability)',
            decision.mode, decision.backend, decision.reason, decision.offload_probability * 100,
        )
        return decision.backend

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
