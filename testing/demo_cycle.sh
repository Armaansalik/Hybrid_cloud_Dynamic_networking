#!/bin/bash
echo "=================================================="
echo " STAGE 1: IDLE — baseline, no load"
echo "=================================================="
curl -w "Response time: %{time_total}s\n" -o /dev/null -s http://10.0.0.100/
sleep 2

echo ""
echo "=================================================="
echo " STAGE 2: TRAFFIC SPIKE STARTING (simulating many users)"
echo "=================================================="
iperf -c 10.0.0.2 -p 5001 -t 20 > /dev/null &
iperf -c 10.0.0.3 -p 5001 -t 20 > /dev/null &
sleep 3

echo ""
echo "=================================================="
echo " STAGE 3: REQUEST DURING SPIKE — watch controller log now"
echo "=================================================="
curl -w "Response time: %{time_total}s\n" -o /dev/null -s http://10.0.0.100/
sleep 2
curl -w "Response time: %{time_total}s\n" -o /dev/null -s http://10.0.0.100/

echo ""
echo " Waiting for spike to finish (~20s)..."
sleep 20

echo ""
echo "=================================================="
echo " STAGE 4: RECOVERY — load has dropped, back to local routing"
echo "=================================================="
curl -w "Response time: %{time_total}s\n" -o /dev/null -s http://10.0.0.100/
echo ""
echo "=== Cycle complete ==="
