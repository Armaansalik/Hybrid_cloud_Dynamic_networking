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


@app.route('/')
def index():
    uptime = round(time.time() - START_TIME, 1)
    # simulated inference latency, just for realism in the response
    sim_latency_ms = round(random.uniform(8, 22), 1)
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--port', type=int, default=80)
    args = parser.parse_args()
    app.config['NAME'] = args.name
    app.config['NODE_TYPE'] = 'cloud-burst-gpu' if 'cloud' in args.name else 'private-gpu'
    app.run(host='0.0.0.0', port=args.port)
