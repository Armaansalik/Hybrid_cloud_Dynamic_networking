import unittest

from controller.routing import choose_backend, offload_probability


class RoutingTests(unittest.TestCase):
    def test_probability_is_zero_at_or_below_threshold(self):
        self.assertEqual(offload_probability(5_000, 5_000), 0.0)
        self.assertEqual(offload_probability(4_999, 5_000), 0.0)

    def test_probability_reaches_one_at_double_threshold(self):
        self.assertEqual(offload_probability(10_000, 5_000), 1.0)

    def test_least_loaded_private_backend_is_selected_without_offload(self):
        name, probability = choose_backend({"h2": 3000, "h3": 1000}, 5000, random_value=0.2)
        self.assertEqual(name, "h3")
        self.assertEqual(probability, 0.0)

    def test_cloud_is_selected_when_load_is_at_double_threshold(self):
        name, probability = choose_backend({"h2": 10_000, "h3": 12_000}, 5_000, random_value=0.1)
        self.assertEqual(name, "h4")
        self.assertEqual(probability, 1.0)

    def test_invalid_threshold_is_rejected(self):
        with self.assertRaises(ValueError):
            offload_probability(5000, 0)


if __name__ == "__main__":
    unittest.main()
