import unittest
from unittest.mock import MagicMock, patch

import requests

import fetch_context


def _json_response(payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


class TestLovdLookup(unittest.TestCase):
    def setUp(self):
        fetch_context._reset_lovd_host_state()

    def tearDown(self):
        fetch_context._reset_lovd_host_state()

    def test_timeout_on_first_term_logs_and_tries_next_term(self):
        side_effects = [
            requests.exceptions.ReadTimeout("first term timed out"),
            _json_response([{"id": "0001", "effect": "pathogenic"}]),
        ]
        with patch.object(fetch_context.requests, "get", side_effect=side_effects) as mock_get, \
             self.assertLogs(fetch_context.logger, level="WARNING") as logs:
            result = fetch_context.get_lovd_variants("SNCA", "A53T")

        self.assertEqual(mock_get.call_count, 2)
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "LOVD")
        self.assertEqual(result["search_term"], "p.(Ala53Thr)")
        self.assertEqual(result["variants_found"], 1)
        self.assertTrue(any("p.Ala53Thr" in msg for msg in logs.output))

    def test_connection_error_on_first_term_tries_next_term(self):
        side_effects = [
            requests.exceptions.ConnectionError("transient reset"),
            _json_response([]),
            _json_response({"data": [{"id": "0002"}]}),
        ]
        with patch.object(fetch_context.requests, "get", side_effect=side_effects) as mock_get, \
             self.assertLogs(fetch_context.logger, level="WARNING"):
            result = fetch_context.get_lovd_variants("SNCA", "A53T")

        self.assertEqual(mock_get.call_count, 3)
        self.assertIsNotNone(result)
        self.assertEqual(result["search_term"], "A53T")
        self.assertEqual(result["variants_found"], 1)

    def test_returns_none_only_after_all_terms_fail(self):
        with patch.object(
            fetch_context.requests,
            "get",
            side_effect=requests.exceptions.ReadTimeout("slow query"),
        ) as mock_get, self.assertLogs(fetch_context.logger, level="WARNING") as logs:
            result = fetch_context.get_lovd_variants("SNCA", "A53T")

        self.assertIsNone(result)
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(len(logs.output), 3)

    def test_dead_host_uses_single_attempt_for_subsequent_variants(self):
        with patch.object(
            fetch_context.requests,
            "get",
            side_effect=requests.exceptions.ConnectTimeout("host unreachable"),
        ) as mock_get, self.assertLogs(fetch_context.logger, level="WARNING"):
            first = fetch_context.get_lovd_variants("SNCA", "A53T")
            self.assertIsNone(first)
            self.assertEqual(mock_get.call_count, 3)

            mock_get.reset_mock()
            second = fetch_context.get_lovd_variants("TTR", "V50M")
            self.assertIsNone(second)
            self.assertEqual(mock_get.call_count, 1)

    def test_host_recovery_clears_down_state_and_resumes_all_terms(self):
        # First variant marks host as down after all 3 connect timeouts.
        with patch.object(
            fetch_context.requests,
            "get",
            side_effect=requests.exceptions.ConnectTimeout("host unreachable"),
        ):
            self.assertIsNone(fetch_context.get_lovd_variants("SNCA", "A53T"))

        # Next variant's probe succeeds (empty list), clearing down state and finding match on term 2.
        recovery_responses = [
            _json_response([]),
            _json_response([{"id": "recovered"}]),
        ]
        with patch.object(fetch_context.requests, "get", side_effect=recovery_responses) as mock_get:
            result = fetch_context.get_lovd_variants("TTR", "V50M")

        self.assertEqual(mock_get.call_count, 2)
        self.assertIsNotNone(result)
        self.assertEqual(result["first_variant"]["id"], "recovered")


if __name__ == "__main__":
    unittest.main()
