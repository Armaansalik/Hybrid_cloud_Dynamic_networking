import os
import tempfile
import unittest

from controller.reliability import (
    BackendTelemetry,
    CounterSnapshot,
    ReliabilityConfig,
    ReliabilityPolicy,
    TelemetryTracker,
    load_reliability_config,
)


def sample(name, load, drop_rate=0.0, health="healthy"):
    return BackendTelemetry(
        name=name,
        bytes_per_sec=load,
        smoothed_bytes_per_sec=load,
        packets_per_sec=100.0,
        drops_per_sec=drop_rate,
        errors_per_sec=0.0,
        drop_rate_pct=drop_rate,
        has_measurement=True,
        health=health,
    )


class TelemetryTrackerTests(unittest.TestCase):
    def test_telemetry_serializes_dashboard_safe_health_values(self):
        telemetry = sample("h2", 1_000)

        serialized = telemetry.as_dict()

        self.assertEqual(serialized["health"], "healthy")
        self.assertEqual(serialized["smoothed_bytes_per_sec"], 1_000)
        self.assertIn("drop_rate_pct", serialized)

    def test_first_sample_establishes_a_zero_rate_baseline(self):
        tracker = TelemetryTracker(alpha=0.4)

        telemetry = tracker.update("h2", CounterSnapshot(1_000, 10, 0, 0), 2.0)

        self.assertEqual(telemetry.bytes_per_sec, 0.0)
        self.assertEqual(telemetry.drop_rate_pct, 0.0)
        self.assertFalse(telemetry.has_measurement)
        self.assertEqual(telemetry.health, "unknown")

    def test_second_sample_calculates_rates_and_ewma(self):
        tracker = TelemetryTracker(alpha=0.4)
        tracker.update("h2", CounterSnapshot(1_000, 10, 0, 0), 2.0)

        telemetry = tracker.update("h2", CounterSnapshot(3_000, 30, 1, 2), 2.0)

        self.assertEqual(telemetry.bytes_per_sec, 1_000.0)
        self.assertEqual(telemetry.smoothed_bytes_per_sec, 1_000.0)
        self.assertEqual(telemetry.packets_per_sec, 10.0)
        self.assertEqual(telemetry.drops_per_sec, 0.5)
        self.assertEqual(telemetry.errors_per_sec, 1.0)
        self.assertAlmostEqual(telemetry.drop_rate_pct, 1 / 21 * 100)
        self.assertEqual(telemetry.health, "warning")

    def test_counter_reset_is_reported_as_zero_not_a_spike(self):
        tracker = TelemetryTracker(alpha=0.4)
        tracker.update("h2", CounterSnapshot(5_000, 50, 5, 0), 2.0)

        telemetry = tracker.update("h2", CounterSnapshot(100, 1, 0, 0), 2.0)

        self.assertEqual(telemetry.bytes_per_sec, 0.0)
        self.assertEqual(telemetry.packets_per_sec, 0.0)
        self.assertFalse(telemetry.has_measurement)


class ReliabilityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = ReliabilityConfig(5_000, 0.4, 0.65, 2, 3, 1.0)

    def test_least_loaded_private_backend_is_used_before_activation(self):
        policy = ReliabilityPolicy(self.config)

        decision = policy.evaluate({"h2": sample("h2", 8_000), "h3": sample("h3", 3_000)}, 0.0)

        self.assertEqual(decision.backend, "h3")
        self.assertEqual(decision.mode, "local")

    def test_single_high_sample_does_not_activate_cloud_offload(self):
        policy = ReliabilityPolicy(self.config)
        private = {"h2": sample("h2", 8_000), "h3": sample("h3", 9_000)}

        decision = policy.evaluate(private, 0.0)

        self.assertEqual(decision.backend, "h2")
        self.assertEqual(decision.mode, "local")
        self.assertEqual(decision.activation_count, 1)

    def test_second_high_sample_activates_gradual_cloud_offload(self):
        policy = ReliabilityPolicy(self.config)
        private = {"h2": sample("h2", 8_000), "h3": sample("h3", 9_000)}
        policy.evaluate(private, 0.0)

        decision = policy.evaluate(private, 0.1)

        self.assertEqual(decision.backend, "h4")
        self.assertEqual(decision.mode, "offloading")
        self.assertAlmostEqual(decision.offload_probability, 0.6)

    def test_drop_rate_warning_forces_cloud_after_activation_window(self):
        policy = ReliabilityPolicy(self.config)
        private = {"h2": sample("h2", 1_000, drop_rate=2.0), "h3": sample("h3", 1_200)}
        policy.evaluate(private, 0.0)

        decision = policy.evaluate(private, 0.99)

        self.assertEqual(decision.backend, "h4")
        self.assertEqual(decision.offload_probability, 1.0)
        self.assertIn("packet loss", decision.reason)

    def test_recovery_requires_three_consecutive_safe_samples(self):
        policy = ReliabilityPolicy(self.config)
        overloaded = {"h2": sample("h2", 8_000), "h3": sample("h3", 9_000)}
        policy.evaluate(overloaded, 0.0)
        policy.evaluate(overloaded, 0.0)
        recovered = {"h2": sample("h2", 3_000), "h3": sample("h3", 3_100)}

        self.assertEqual(policy.evaluate(recovered, 0.0).mode, "offloading")
        self.assertEqual(policy.evaluate(recovered, 0.0).mode, "offloading")
        decision = policy.evaluate(recovered, 0.0)

        self.assertEqual(decision.mode, "local")
        self.assertEqual(decision.backend, "h2")


class ReliabilityConfigurationTests(unittest.TestCase):
    def test_invalid_configuration_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "reliability.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("not-json")

            config = load_reliability_config(path)

        self.assertEqual(config.threshold_bytes_per_sec, 5_000)
        self.assertEqual(config.activation_samples, 2)


if __name__ == "__main__":
    unittest.main()
