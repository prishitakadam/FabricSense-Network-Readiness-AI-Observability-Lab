import unittest

from fabric_readiness.experiment import Experiment


class FakeOperations:
    def __init__(self):
        self.events = []
        self.benchmark_calls = 0

    def preflight(self):
        self.events.append("preflight")

    def benchmark(self):
        self.benchmark_calls += 1
        if self.benchmark_calls == 2:
            raise RuntimeError("iperf3 stopped unexpectedly")
        return {"throughput_mbps": 800.0, "retransmits": 0, "intervals_mbps": []}

    def error_count(self):
        return 0.0

    def set_link_state(self, state):
        self.events.append(f"set:{state}")

    def wait_link_state(self, expected):
        self.events.append(f"wait:{expected}")
        return True

    def telemetry_is_fresh(self):
        return True


class ExperimentTests(unittest.TestCase):
    def test_restores_link_when_fault_window_benchmark_fails(self):
        operations = FakeOperations()
        experiment = Experiment(
            operations,
            {
                "minimum_baseline_mbps": 100.0,
                "minimum_degraded_ratio": 0.7,
                "minimum_recovered_ratio": 0.9,
                "maximum_recovery_seconds": 30.0,
                "maximum_error_delta": 0.0,
            },
            node="leaf1",
            interface="ethernet-1/49",
        )

        result = experiment.run()

        self.assertEqual(result["result"], "INCONCLUSIVE")
        self.assertIn("iperf3 stopped unexpectedly", result["error"])
        self.assertEqual(
            operations.events,
            ["preflight", "set:disable", "wait:0", "set:enable", "wait:1"],
        )


if __name__ == "__main__":
    unittest.main()
