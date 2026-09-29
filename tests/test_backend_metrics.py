import unittest

from backend.server_app import app, reset_metrics


class BackendMetricsTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, NAME="private-gpu-A", NODE_TYPE="private-gpu")
        reset_metrics()
        self.client = app.test_client()

    def test_metrics_reports_requests_after_service_calls(self):
        response = self.client.get("/")
        metrics = self.client.get("/metrics").get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(metrics["request_count"], 1)
        self.assertEqual(metrics["success_count"], 1)
        self.assertEqual(metrics["served_by"], "private-gpu-A")
        self.assertIn("average_simulated_latency_ms", metrics)

    def test_health_and_metrics_requests_do_not_count_as_inference_requests(self):
        self.client.get("/health")
        metrics = self.client.get("/metrics").get_json()

        self.assertEqual(metrics["request_count"], 0)


if __name__ == "__main__":
    unittest.main()
