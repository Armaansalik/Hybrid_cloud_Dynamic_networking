import unittest
from pathlib import Path


class DashboardContractTests(unittest.TestCase):
    def test_dashboard_has_reliability_panel_and_safe_optional_status_handling(self):
        html = Path("dashboard/index.html").read_text(encoding="utf-8")

        self.assertIn('id="reliabilityPanel"', html)
        self.assertIn("data.reliability ||", html)
        self.assertIn("smoothed_bytes_per_sec", html)
        self.assertIn("drop_rate_pct", html)


if __name__ == "__main__":
    unittest.main()
