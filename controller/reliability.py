"""Pure telemetry and cloud-offload policy for Hybrid Cloud-SDN.

This module intentionally has no Ryu dependency.  It can therefore be tested
without Mininet or an OpenFlow switch and is adapted by the controller.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


DEFAULT_CONFIG = {
    "threshold_bytes_per_sec": 5000,
    "ewma_alpha": 0.4,
    "recovery_threshold_ratio": 0.65,
    "activation_samples": 2,
    "recovery_samples": 3,
    "drop_rate_warning_pct": 1.0,
}


@dataclass(frozen=True)
class ReliabilityConfig:
    threshold_bytes_per_sec: float
    ewma_alpha: float
    recovery_threshold_ratio: float
    activation_samples: int
    recovery_samples: int
    drop_rate_warning_pct: float

    @classmethod
    def from_mapping(cls, values):
        merged = dict(DEFAULT_CONFIG)
        merged.update(values or {})
        config = cls(
            threshold_bytes_per_sec=float(merged["threshold_bytes_per_sec"]),
            ewma_alpha=float(merged["ewma_alpha"]),
            recovery_threshold_ratio=float(merged["recovery_threshold_ratio"]),
            activation_samples=int(merged["activation_samples"]),
            recovery_samples=int(merged["recovery_samples"]),
            drop_rate_warning_pct=float(merged["drop_rate_warning_pct"]),
        )
        if config.threshold_bytes_per_sec <= 0:
            raise ValueError("threshold_bytes_per_sec must be greater than zero")
        if not 0 < config.ewma_alpha <= 1:
            raise ValueError("ewma_alpha must be in the range (0, 1]")
        if not 0 < config.recovery_threshold_ratio <= 1:
            raise ValueError("recovery_threshold_ratio must be in the range (0, 1]")
        if config.activation_samples < 1 or config.recovery_samples < 1:
            raise ValueError("sample counts must be at least one")
        if config.drop_rate_warning_pct < 0:
            raise ValueError("drop_rate_warning_pct cannot be negative")
        return config


def load_reliability_config(path):
    """Load valid JSON settings, falling back to documented defaults."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return ReliabilityConfig.from_mapping(json.load(handle))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return ReliabilityConfig.from_mapping(DEFAULT_CONFIG)


@dataclass(frozen=True)
class CounterSnapshot:
    byte_count: int
    packet_count: int
    dropped_count: int
    error_count: int


@dataclass(frozen=True)
class BackendTelemetry:
    name: str
    bytes_per_sec: float
    smoothed_bytes_per_sec: float
    packets_per_sec: float
    drops_per_sec: float
    errors_per_sec: float
    drop_rate_pct: float
    has_measurement: bool
    health: str

    def as_dict(self):
        return {
            "bytes_per_sec": round(self.bytes_per_sec, 1),
            "smoothed_bytes_per_sec": round(self.smoothed_bytes_per_sec, 1),
            "packets_per_sec": round(self.packets_per_sec, 1),
            "drops_per_sec": round(self.drops_per_sec, 1),
            "errors_per_sec": round(self.errors_per_sec, 1),
            "drop_rate_pct": round(self.drop_rate_pct, 3),
            "has_measurement": self.has_measurement,
            "health": self.health,
        }


@dataclass(frozen=True)
class RoutingDecision:
    backend: str
    mode: str
    reason: str
    offload_probability: float
    activation_count: int
    recovery_count: int


class TelemetryTracker:
    """Derive rate telemetry from monotonically increasing port counters."""

    def __init__(self, alpha):
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in the range (0, 1]")
        self.alpha = float(alpha)
        self._previous = {}
        self._smoothed = {}

    def update(self, name, current, interval_seconds):
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        previous = self._previous.get(name)
        self._previous[name] = current
        if previous is None or self._counter_reset(previous, current):
            self._smoothed.pop(name, None)
            return self._empty_telemetry(name)

        byte_delta = current.byte_count - previous.byte_count
        packet_delta = current.packet_count - previous.packet_count
        dropped_delta = current.dropped_count - previous.dropped_count
        error_delta = current.error_count - previous.error_count
        bytes_per_sec = byte_delta / float(interval_seconds)
        packets_per_sec = packet_delta / float(interval_seconds)
        drops_per_sec = dropped_delta / float(interval_seconds)
        errors_per_sec = error_delta / float(interval_seconds)
        previous_smoothed = self._smoothed.get(name, bytes_per_sec)
        smoothed = self.alpha * bytes_per_sec + (1.0 - self.alpha) * previous_smoothed
        self._smoothed[name] = smoothed
        drop_rate_pct = dropped_delta / float(max(packet_delta + dropped_delta, 1)) * 100.0
        health = "warning" if dropped_delta > 0 or error_delta > 0 else "healthy"
        return BackendTelemetry(
            name=name,
            bytes_per_sec=bytes_per_sec,
            smoothed_bytes_per_sec=smoothed,
            packets_per_sec=packets_per_sec,
            drops_per_sec=drops_per_sec,
            errors_per_sec=errors_per_sec,
            drop_rate_pct=drop_rate_pct,
            has_measurement=True,
            health=health,
        )

    @staticmethod
    def _counter_reset(previous, current):
        return any(
            getattr(current, field) < getattr(previous, field)
            for field in ("byte_count", "packet_count", "dropped_count", "error_count")
        )

    @staticmethod
    def _empty_telemetry(name):
        return BackendTelemetry(name, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, "unknown")


class ReliabilityPolicy:
    """Hysteresis policy that routes only new service connections."""

    def __init__(self, config):
        self.config = config
        self.mode = "local"
        self.activation_count = 0
        self.recovery_count = 0
        self.reason = "private capacity available"

    def evaluate(self, private_telemetry, random_value):
        if not private_telemetry:
            raise ValueError("at least one private backend is required")
        if not 0 <= random_value < 1:
            raise ValueError("random_value must be in the range [0, 1)")
        best_name = min(
            private_telemetry,
            key=lambda name: private_telemetry[name].smoothed_bytes_per_sec,
        )
        best = private_telemetry[best_name]
        drop_warning = any(
            telemetry.drop_rate_pct >= self.config.drop_rate_warning_pct
            for telemetry in private_telemetry.values()
            if telemetry.has_measurement
        )
        overloaded = best.smoothed_bytes_per_sec >= self.config.threshold_bytes_per_sec or drop_warning
        recovered = (
            best.smoothed_bytes_per_sec < self.config.threshold_bytes_per_sec * self.config.recovery_threshold_ratio
            and not drop_warning
        )
        self._update_mode(overloaded, recovered, drop_warning)
        probability = 1.0 if drop_warning and self.mode == "offloading" else self._offload_probability(best.smoothed_bytes_per_sec)
        backend = "h4" if self.mode == "offloading" and probability > random_value else best_name
        return RoutingDecision(
            backend=backend,
            mode=self.mode,
            reason=self.reason,
            offload_probability=probability if self.mode == "offloading" else 0.0,
            activation_count=self.activation_count,
            recovery_count=self.recovery_count,
        )

    def _update_mode(self, overloaded, recovered, drop_warning):
        if self.mode == "local":
            self.recovery_count = 0
            self.activation_count = self.activation_count + 1 if overloaded else 0
            if self.activation_count >= self.config.activation_samples:
                self.mode = "offloading"
                self.reason = "packet loss warning" if drop_warning else "sustained private congestion"
            else:
                self.reason = "waiting for sustained overload" if overloaded else "private capacity available"
            return

        self.activation_count = self.config.activation_samples if overloaded else 0
        self.recovery_count = self.recovery_count + 1 if recovered else 0
        if self.recovery_count >= self.config.recovery_samples:
            self.mode = "local"
            self.activation_count = 0
            self.reason = "sustained private recovery"
        elif drop_warning:
            self.reason = "packet loss warning"
        elif recovered:
            self.reason = "waiting for sustained private recovery"
        else:
            self.reason = "private congestion remains"

    def _offload_probability(self, load):
        if load <= self.config.threshold_bytes_per_sec:
            return 0.0
        return min(1.0, (load - self.config.threshold_bytes_per_sec) / self.config.threshold_bytes_per_sec)
