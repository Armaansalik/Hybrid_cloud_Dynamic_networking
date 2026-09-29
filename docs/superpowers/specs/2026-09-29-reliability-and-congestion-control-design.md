# Reliability and Congestion-Control Design

## Purpose

Extend the Hybrid Cloud-SDN prototype so it can demonstrate safe, measurable cloud bursting under traffic congestion. The controller must make stable decisions for new TCP connections, expose network-health evidence, and preserve the existing virtual-IP flow and dashboard experience.

## Scope and success criteria

The project currently chooses h2, h3, or h4 from instantaneous byte-rate samples. This increment adds a small reliability subsystem that:

- reads OpenFlow packet, drop, error, and byte counters;
- smooths byte-rate data with an EWMA;
- enters cloud offload only after sustained overload or a drop-rate warning;
- exits cloud offload only after sustained private recovery;
- keeps existing TCP flows unchanged and steers only new virtual-IP flows;
- exposes the measured state through the existing Ryu `/status` API and dashboard; and
- supplies repeatable HTTP and network-loss test instructions and automated policy tests.

This is a research prototype, not a guarantee of zero packet loss. It must report loss and avoid queue overflow earlier; TCP is responsible for retransmission of application data where applicable.

## Non-goals

- Do not replace Ryu, Mininet, Open vSwitch, or the virtual IP.
- Do not add Node.js, C++, Redis, PostgreSQL, Prometheus, or an AWS account.
- Do not migrate existing connections between backends.
- Do not claim a fixed requests-per-second target or zero packet loss without an experiment result.
- Do not change the default topology or its 10 Mbps cloud link.

## Configuration

Create `config/reliability.json` as the single source of tunable reliability values:

```json
{
  "threshold_bytes_per_sec": 5000,
  "ewma_alpha": 0.4,
  "recovery_threshold_ratio": 0.65,
  "activation_samples": 2,
  "recovery_samples": 3,
  "drop_rate_warning_pct": 1.0
}
```

The runtime threshold remains adjustable through the existing `/set-threshold` endpoint. That API updates the in-memory threshold only; it must not rewrite the user configuration file.

## Architecture

### Telemetry

For every backend-facing switch port, the controller retains the previous OpenFlow `PortStats` counters. On each monitor interval it derives:

- bytes per second from the byte-counter delta;
- packets per second from the packet-counter delta;
- drops per second from the dropped-packet-counter delta;
- errors per second from the error-counter delta; and
- drop-rate percent: `drops / max(packets + drops, 1) * 100`.

The EWMA is calculated only from successive samples. A first sample produces zero rates and establishes a baseline, so a counter reset cannot create a false traffic spike.

### Policy

`controller/reliability.py` is a Ryu-independent pure-Python module. It holds the policy state and accepts a mapping of private backend telemetry.

- In normal mode, choose the least-loaded private backend.
- An overload sample occurs when the least-loaded private EWMA is at or above the high threshold, or any selected private backend drop rate is at or above the warning percentage.
- Cloud offload activates after `activation_samples` consecutive overload samples.
- While active, new flows are gradually sent to h4 with the existing probability curve, calculated from smoothed load. A packet-drop warning causes full cloud offload for new flows.
- Recovery requires `recovery_samples` consecutive samples below `threshold * recovery_threshold_ratio` with no drop-rate warning.
- Existing Ryu flow entries remain untouched; only an arriving, unmatched TCP service request invokes the policy.

The policy returns a route decision and a human-readable reason. The controller records state transitions in its existing event log, not every sample, to keep the dashboard readable.

### API and dashboard

The Ryu `/status` response adds a `reliability` object per backend containing smoothed B/s, packets/s, drops/s, errors/s, drop-rate percentage, and health state. It also includes global policy mode, consecutive activation/recovery counts, and the reason for the most recent decision.

The dashboard retains the existing topology. It adds a compact reliability panel that shows global policy mode and backend health metrics. It must handle an unavailable or older controller response by displaying `--` rather than throwing a JavaScript error.

### Backend and test evidence

The Flask demo backend gains a `/metrics` endpoint that reports process-local request count, successful requests, average simulated latency, and uptime. The existing `/` response and `/health` route stay compatible.

The load-test script records HTTP status, total latency, backend distribution, and failure count. A separate documented Mininet command uses `iperf` UDP mode to report packet loss independently of HTTP success. These scripts are for experiment evidence; the controller does not query the isolated Mininet backend metrics endpoint directly.

## Error handling

- Invalid or missing reliability configuration falls back to documented safe defaults and writes a controller warning.
- Negative counter deltas, produced by switch counter resets, are treated as zero and reset the baseline.
- Missing telemetry for a backend results in an `unknown` health state and must not fabricate a loss percentage.
- Invalid API thresholds continue to return an explicit error instead of modifying the active policy.

## Validation

Unit tests cover the first counter sample, normal deltas, counter reset, EWMA calculation, drop-rate warning, delayed activation, delayed recovery, and selection of the least-loaded private node. Existing routing tests remain unchanged or are updated only for their public equivalent behavior.

CI compiles the new modules and executes all unit tests. The Docker test profile must run the same tests. Manual Mininet validation confirms a virtual-IP HTTP request before load, a stable h4 offload during sustained load, and private recovery after load stops.
