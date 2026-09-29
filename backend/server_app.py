#!/usr/bin/env python3
"""
Simulated GPU inference node service. Run on each Mininet host to
represent a real inference backend (on-prem GPU node or cloud-burst
GPU node) responding to routed requests.
"""
import argparse
import time
import random
from flask import Flask, jsonify

app = Flask(__name__)
START_TIME = time.time()
REQUEST_COUNT = 0
SUCCESS_COUNT = 0
TOTAL_SIMULATED_LATENCY_MS = 0.0

def reset_metrics():
    """Reset process-local counters; used by automated tests only."""
    global REQUEST_COUNT, SUCCESS_COUNT, TOTAL_SIMULATED_LATENCY_MS
    REQUEST_COUNT = 0
    SUCCESS_COUNT = 0
    TOTAL_SIMULATED_LATENCY_MS = 0.0


@app.route('/')
def index():
    uptime = round(time.time() - START_TIME, 1)
    global REQUEST_COUNT, SUCCESS_COUNT, TOTAL_SIMULATED_LATENCY_MS
    sim_latency_ms = round(random.uniform(8, 22), 1)
    REQUEST_COUNT += 1
    SUCCESS_COUNT += 1
    TOTAL_SIMULATED_LATENCY_MS += sim_latency_ms
    return jsonify({
        'served_by': app.config['NAME'],
        'node_type': app.config.get('NODE_TYPE', 'inference-node'),
        'model': 'resnet50-sim',
        'simulated_inference_latency_ms': sim_latency_ms,
        'uptime_sec': uptime,
    })


@app.route('/health')
def health():
    return "ok\n"

@app.route('/metrics')
def metrics():
    average_latency = TOTAL_SIMULATED_LATENCY_MS / REQUEST_COUNT if REQUEST_COUNT else 0.0
    return jsonify({
        'served_by': app.config.get('NAME', 'unconfigured'),
        'node_type': app.config.get('NODE_TYPE', 'inference-node'),
        'request_count': REQUEST_COUNT,
        'success_count': SUCCESS_COUNT,
        'average_simulated_latency_ms': round(average_latency, 1),
        'uptime_sec': round(time.time() - START_TIME, 1),
    })



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--port', type=int, default=80)
    args = parser.parse_args()
    app.config['NAME'] = args.name
    app.config['NODE_TYPE'] = 'cloud-burst-gpu' if 'cloud' in args.name else 'private-gpu'
    app.run(host='0.0.0.0', port=args.port)
