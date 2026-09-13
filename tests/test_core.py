import json
import unittest

from fabric_readiness.core import (
    IperfError,
    analyze_fault_intervals,
    evaluate,
    parse_iperf,
    parse_prometheus_value,
)


class IperfParsingTests(unittest.TestCase):
    def test_parses_receiver_throughput_retransmits_and_intervals(self):
        payload = json.dumps(
            {
                "intervals": [
                    {"sum": {"start": 0, "end": 1, "bits_per_second": 800_000_000}},
                    {"sum": {"start": 1, "end": 2, "bits_per_second": 600_000_000}},
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
                "intervals": [
                    {"start": 0.0, "end": 1.0, "throughput_mbps": 800.0},
                    {"start": 1.0, "end": 2.0, "throughput_mbps": 600.0},
                ],
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


class FaultIntervalAnalysisTests(unittest.TestCase):
    def test_measures_interruption_and_sustained_recovery_from_fault_time(self):
        rates = [100, 100, 0, 40, 80, 85, 90, 95]
        intervals = [
            {"start": float(index), "end": float(index + 1), "throughput_mbps": rate}
            for index, rate in enumerate(rates)
        ]

        result = analyze_fault_intervals(
            intervals,
            baseline_mbps=100,
            fault_offset=2,
            restore_offset=6,
            minimum_degraded_ratio=0.7,
            sustained_intervals=2,
        )

        self.assertEqual(
            result,
            {
                "traffic_recovered": True,
                "recovery_seconds": 2.0,
                "maximum_interruption_seconds": 2.0,
                "degraded_throughput_mbps": 82.5,
                "recovered_throughput_mbps": 92.5,
            },
        )


class ReadinessEvaluationTests(unittest.TestCase):
    policy = {
        "minimum_baseline_mbps": 100.0,
        "minimum_degraded_ratio": 0.7,
        "minimum_recovered_ratio": 0.9,
        "maximum_recovery_seconds": 30.0,
        "maximum_error_delta": 0.0,
    }

    def healthy_evidence(self):
        return {
            "preflight_ok": True,
            "telemetry_fresh": True,
            "fault_observed": True,
            "traffic_recovered": True,
            "restored": True,
            "baseline_throughput_mbps": 800.0,
            "degraded_throughput_mbps": 600.0,
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

    def test_returns_fail_when_degraded_path_lacks_capacity(self):
        evidence = self.healthy_evidence()
        evidence["degraded_throughput_mbps"] = 400.0

        result, checks = evaluate(evidence, self.policy)

        self.assertEqual(result, "FAIL")
        self.assertIn(
            "degraded_throughput",
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
