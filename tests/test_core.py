import json
import unittest

from fabric_readiness.core import (
    IperfError,
    evaluate,
    parse_iperf,
    parse_prometheus_value,
)


class IperfParsingTests(unittest.TestCase):
    def test_parses_receiver_throughput_retransmits_and_intervals(self):
        payload = json.dumps(
            {
                "intervals": [
                    {"sum": {"bits_per_second": 800_000_000}},
                    {"sum": {"bits_per_second": 600_000_000}},
                ],
                "end": {
                    "sum_sent": {"bits_per_second": 710_000_000, "retransmits": 7},
                    "sum_received": {"bits_per_second": 700_000_000},
                },
            }
        )

        self.assertEqual(
            parse_iperf(payload),
            {
                "throughput_mbps": 700.0,
                "retransmits": 7,
                "intervals_mbps": [800.0, 600.0],
            },
        )

    def test_rejects_iperf_error_payload(self):
        with self.assertRaisesRegex(IperfError, "unable to connect"):
            parse_iperf('{"error": "unable to connect"}')


class PrometheusParsingTests(unittest.TestCase):
    def test_parses_single_vector_value(self):
        payload = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [{"metric": {}, "value": [1_700_000_000, "1"]}],
            },
        }

        self.assertEqual(parse_prometheus_value(payload), 1.0)

    def test_rejects_empty_vector(self):
        payload = {"status": "success", "data": {"result": []}}

        with self.assertRaisesRegex(ValueError, "exactly one result"):
            parse_prometheus_value(payload)


class ReadinessEvaluationTests(unittest.TestCase):
    policy = {
        "minimum_baseline_mbps": 100.0,
        "minimum_recovered_ratio": 0.9,
        "maximum_recovery_seconds": 30.0,
        "maximum_error_delta": 0.0,
    }

    def healthy_evidence(self):
        return {
            "preflight_ok": True,
            "telemetry_fresh": True,
            "fault_observed": True,
            "restored": True,
            "baseline_throughput_mbps": 800.0,
            "recovered_throughput_mbps": 760.0,
            "recovery_seconds": 8.0,
            "error_delta": 0.0,
        }

    def test_returns_pass_when_every_rule_passes(self):
        result, checks = evaluate(self.healthy_evidence(), self.policy)

        self.assertEqual(result, "PASS")
        self.assertTrue(all(check["status"] == "PASS" for check in checks))

    def test_returns_fail_for_valid_slow_recovery(self):
        evidence = self.healthy_evidence()
        evidence["recovery_seconds"] = 45.0

        result, checks = evaluate(evidence, self.policy)

        self.assertEqual(result, "FAIL")
        self.assertIn(
            "recovery_time",
            [check["name"] for check in checks if check["status"] == "FAIL"],
        )

    def test_returns_inconclusive_when_telemetry_is_not_trustworthy(self):
        evidence = self.healthy_evidence()
        evidence["telemetry_fresh"] = False

        result, checks = evaluate(evidence, self.policy)

        self.assertEqual(result, "INCONCLUSIVE")
        self.assertIn(
            "telemetry_freshness",
            [check["name"] for check in checks if check["status"] == "INCONCLUSIVE"],
        )


if __name__ == "__main__":
    unittest.main()
