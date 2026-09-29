# Reliability testing

Start the local WSL demonstration first:

```bash
cd ~/HybridCloudSDN
./start_all.sh
```

In the Mininet prompt, record a baseline virtual-service result:

```bash
h1 curl -sS --connect-timeout 5 http://10.0.0.100/
h1 bash testing/reliability_load_test.sh 30
```

The summary reports HTTP delivery evidence:

```text
HTTP summary: requested=<n> success=<n> failed=<n> mean_latency_ms=<value>
Backend distribution: private-gpu-A=<n> private-gpu-B=<n> cloud-gpu-burst=<n>
```

To make one private node appear busier, run an `iperf` TCP server on the
opposite node and then send traffic from the client. For example, to favour
h3 as the least-loaded private node:

```bash
h2 iperf -s -p 5001 &
h1 iperf -c 10.0.0.2 -p 5001 -t 20 &
```

Then repeat the virtual-IP request or the HTTP reliability script. Sustained
private congestion activates h4 for new connections; after several safe
monitoring samples, private routing resumes.

## Independent packet-loss experiment

HTTP success is not proof that no network packet was lost. Measure network
loss separately with UDP `iperf`:

```bash
h2 iperf -s -u -p 5002 &
h1 iperf -c 10.0.0.2 -u -p 5002 -b 8M -t 20
```

The final `iperf` line reports datagrams and loss percentage. Save that output
with the dashboard status and the HTTP summary as experiment evidence. TCP can
retransmit lost packets; packet loss can still increase response latency.

The current topology limits the cloud path to 10 Mbps. Treat the outcome as a
repeatable SDN congestion-control experiment, not a claim of a fixed RPS value
or guaranteed zero packet loss.
