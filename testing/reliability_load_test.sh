#!/usr/bin/env bash
# Run inside Mininet: h1 bash testing/reliability_load_test.sh [request-count]
set -euo pipefail

REQUESTS="${1:-30}"
VIRTUAL_IP="${VIRTUAL_IP:-10.0.0.100}"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

success=0
failed=0
total_latency=0
declare -A backends=([private-gpu-A]=0 [private-gpu-B]=0 [cloud-gpu-burst]=0)

for request in $(seq 1 "$REQUESTS"); do
  result="$(curl -sS --connect-timeout 5 -w '\n%{http_code} %{time_total}' "http://${VIRTUAL_IP}/" 2>&1 || true)"
  body="$(printf '%s\n' "$result" | sed '$d')"
  summary="$(printf '%s\n' "$result" | tail -n 1)"
  status="$(printf '%s\n' "$summary" | awk '{print $1}')"
  latency="$(printf '%s\n' "$summary" | awk '{print $2}')"
  if [[ "$status" =~ ^2[0-9][0-9]$ ]]; then
    success=$((success + 1))
    total_latency="$(awk -v total="$total_latency" -v value="$latency" 'BEGIN { print total + value }')"
    served_by="$(printf '%s' "$body" | sed -n 's/.*"served_by"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
    if [[ -n "${backends[$served_by]+known}" ]]; then
      backends[$served_by]=$((backends[$served_by] + 1))
    fi
  else
    failed=$((failed + 1))
  fi
done

mean_latency_ms="$(awk -v total="$total_latency" -v count="$success" 'BEGIN { if (count) printf "%.2f", total / count * 1000; else print "--" }')"
echo "HTTP summary: requested=${REQUESTS} success=${success} failed=${failed} mean_latency_ms=${mean_latency_ms}"
echo "Backend distribution: private-gpu-A=${backends[private-gpu-A]} private-gpu-B=${backends[private-gpu-B]} cloud-gpu-burst=${backends[cloud-gpu-burst]}"
