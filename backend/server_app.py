#!/usr/bin/env python3
"""
Minimal backend service used to represent a "real" server during the demo.
Run this on h2, h3, and h4 inside their Mininet host shells.

Examples (run inside the Mininet CLI, one per host):
    mininet> h2 python3 backend/server_app.py --name private-A --port 80 &
    mininet> h3 python3 backend/server_app.py --name private-B --port 80 &
    mininet> h4 python3 backend/server_app.py --name cloud-node --port 80 &
"""
import argparse
import time
from flask import Flask

app = Flask(__name__)
START_TIME = time.time()


@app.route('/')
def index():
    uptime = round(time.time() - START_TIME, 1)
    return f"Handled by backend: {app.config['NAME']} (uptime {uptime}s)\n"


@app.route('/health')
def health():
    return "ok\n"


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True, help="label shown in responses, e.g. private-A")
    parser.add_argument('--port', type=int, default=80)
    args = parser.parse_args()
    app.config['NAME'] = args.name
    app.run(host='0.0.0.0', port=args.port)
