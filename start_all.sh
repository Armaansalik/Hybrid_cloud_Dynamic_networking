#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
PROJECT_DIR="$PWD"
VENV_DIR="$PROJECT_DIR/.venv"
API_PORT=8082
DASHBOARD_PORT=8081
CONTROLLER_PID=""
DASHBOARD_PID=""

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "Project environment is missing. Run ./setup.sh once, then retry."
  exit 1
fi

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  [ -n "$CONTROLLER_PID" ] && kill "$CONTROLLER_PID" 2>/dev/null || true
  [ -n "$DASHBOARD_PID" ] && kill "$DASHBOARD_PID" 2>/dev/null || true
  rm -f logs/controller.pid logs/dashboard.pid
  exit "$exit_code"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p logs data
sudo mn -c >/dev/null 2>&1 || true
source "$VENV_DIR/bin/activate"
nohup ryu-manager controller/hybrid_lb_controller.py --wsapi-port "$API_PORT" > logs/controller.log 2>&1 &
CONTROLLER_PID=$!
echo "$CONTROLLER_PID" > logs/controller.pid
sleep 3
cd dashboard
nohup python3 -m http.server "$DASHBOARD_PORT" > "$PROJECT_DIR/logs/dashboard.log" 2>&1 &
DASHBOARD_PID=$!
echo "$DASHBOARD_PID" > "$PROJECT_DIR/logs/dashboard.pid"
cd "$PROJECT_DIR"
sleep 1
echo "Controller API: http://127.0.0.1:$API_PORT/status"
echo "Dashboard: http://localhost:$DASHBOARD_PORT/index.html"
echo "Starting Mininet. In its prompt run: h1 bash testing/demo_cycle.sh"
sudo HYBRID_BACKEND_PYTHON="$VENV_DIR/bin/python" python3 topology/auto_deploy_topology.py