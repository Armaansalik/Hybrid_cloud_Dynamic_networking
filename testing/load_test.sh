#!/bin/bash
# Run this INSIDE the Mininet CLI on the client host, e.g.:
#   mininet> h1 bash testing/load_test.sh
#
# Phase 1: light traffic  -> requests should stay on private backends (h2/h3)
# Phase 2: heavy traffic  -> private backends get loaded, requests should
#           start switching to the cloud backend (h4) automatically.
#
# Watch the Ryu controller's terminal output while this runs -- it prints
# "[LOCAL] routing to ..." and "[THRESHOLD EXCEEDED] ... CLOUD OFFLOAD" lines.

echo "=== Phase 1: light load (10 requests, 1s apart) ==="
for i in $(seq 1 10); do
  curl -s http://10.0.0.100/
  sleep 1
done

echo ""
echo "=== Phase 2: simulated traffic spike (200 rapid parallel requests) ==="
for i in $(seq 1 200); do
  curl -s http://10.0.0.100/ &
done
wait

echo ""
echo "=== Phase 3: cooldown, back to light load (10 requests, 1s apart) ==="
for i in $(seq 1 10); do
  curl -s http://10.0.0.100/
  sleep 1
done

echo ""
echo "Done. Compare which backend name appears in the responses during"
echo "Phase 1/3 (should mostly be private-A/private-B) vs Phase 2"
echo "(should start showing cloud-node once the threshold is crossed)."
