#!/bin/bash
set -e
cd "$(dirname "$0")"
source venv/bin/activate
mkdir -p logs data

echo "=== Stopping previous controller/dashboard (if running) ==="
[ -f logs/controller.pid ] && kill "$(cat logs/controller.pid)" 2>/dev/null || true
[ -f logs/dashboard.pid ] && kill "$(cat logs/dashboard.pid)" 2>/dev/null || true
sleep 2

echo "=== Starting controller with latest code ==="
nohup ryu-manager controller/hybrid_lb_controller.py > logs/controller.log 2>&1 &
echo $! > logs/controller.pid

echo "=== Starting dashboard with latest code ==="
cd dashboard
nohup python3 -m http.server 8081 > ../logs/dashboard.log 2>&1 &
echo $! > ../logs/dashboard.pid
cd ..

sleep 2
echo "=== Redeploy complete ==="
