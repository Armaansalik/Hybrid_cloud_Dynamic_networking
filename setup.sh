#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3.8 >/dev/null 2>&1; then
  echo "Python 3.8 is required for Ryu 4.34. Install it in WSL, then retry."
  exit 1
fi

python3.8 -m venv .venv
.venv/bin/python -m pip install --upgrade "pip==23.3.2" "setuptools==59.6.0" "wheel==0.41.3"
.venv/bin/python -m pip install --no-build-isolation -r requirements.txt
mkdir -p logs data

echo "Environment created at $(pwd)/.venv"
echo "Next: ./start_all.sh"
