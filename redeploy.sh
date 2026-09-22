#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
PROJECT_DIR="$PWD"
VENV_DIR="$PROJECT_DIR/.venv"
API_PORT=8082
DASHBOARD_PORT=8081

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "Project environment is missing. Run ./setup.sh once, then retry."
  exit 1
fi

mkdir -p logs data
source "$VENV_DIR/bin/activate"
[ -f logs/controller.pid ] && kill "$(cat logs/controller.pid)" 2>/dev/null || true
[ -f logs/dashboard.pid ] && kill "$(cat logs/dashboard.pid)" 2>/dev/null || true

nohup ryu-manager controller/hybrid_lb_controller.py --wsapi-port "$API_PORT" > logs/controller.log 2>&1 &
echo $! > logs/controller.pid
cd dashboard
nohup python3 -m http.server "$DASHBOARD_PORT" > "$PROJECT_DIR/logs/dashboard.log" 2>&1 &
echo $! > "$PROJECT_DIR/logs/dashboard.pid"
cd "$PROJECT_DIR"
sleep 2
echo "Redeployed controller API on $API_PORT and dashboard on $DASHBOARD_PORT."
