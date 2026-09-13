import unittest

from fabric_readiness.experiment import Experiment, LabOperations


class FakeOperations:
    def __init__(self):
        self.events = []
        self.benchmark_calls = 0
        self.clock = 0.0

    def preflight(self):
        self.events.append("preflight")

    def benchmark(self):
        self.benchmark_calls += 1
        return {"throughput_mbps": 100.0, "retransmits": 0, "intervals": []}

    def start_fault_benchmark(self, seconds):
        self.events.append(f"start_traffic:{seconds}")
        return "process"

    def finish_fault_benchmark(self, process):
        self.events.append(f"finish_traffic:{process}")
        return {
            "throughput_mbps": 80.0,
            "retransmits": 0,
            "intervals": [
                {"start": 0.0, "end": 1.0, "throughput_mbps": 100.0},
                {"start": 1.0, "end": 2.0, "throughput_mbps": 100.0},
                {"start": 2.0, "end": 3.0, "throughput_mbps": 0.0},
                {"start": 3.0, "end": 4.0, "throughput_mbps": 40.0},
                {"start": 4.0, "end": 5.0, "throughput_mbps": 80.0},
                {"start": 5.0, "end": 6.0, "throughput_mbps": 85.0},
                {"start": 6.0, "end": 7.0, "throughput_mbps": 90.0},
                {"start": 7.0, "end": 8.0, "throughput_mbps": 95.0},
            ],
        }

    def error_count(self):
        return 0.0

    def set_link_state(self, state):
        self.events.append(f"set:{state}")

    def wait_link_state(self, expected):
        self.events.append(f"wait:{expected}")
        return True

    def telemetry_is_fresh(self):
        return True

    def pause(self, seconds):
        self.events.append(f"pause:{seconds}")
        self.clock += seconds

    def monotonic(self):
        return self.clock


class ExperimentTests(unittest.TestCase):
    policy = {
        "minimum_baseline_mbps": 50.0,
        "minimum_degraded_ratio": 0.7,
        "minimum_recovered_ratio": 0.9,
        "maximum_recovery_seconds": 30.0,
        "maximum_error_delta": 0.0,
    }

    timing = {
        "pre_fault_seconds": 2,
        "fault_hold_seconds": 4,
        "fault_traffic_seconds": 8,
        "sustained_recovery_intervals": 2,
    }

    def test_disables_link_while_fault_benchmark_is_running(self):
        operations = FakeOperations()
        experiment = Experiment(
            operations,
            self.policy,
            node="leaf1",
            interface="ethernet-1/49",
            timing=self.timing,
        )

        result = experiment.run()

        self.assertEqual(result["result"], "PASS")
        self.assertEqual(
            operations.events,
            [
                "preflight",
                "start_traffic:8",
                "pause:2.0",
                "set:disable",
                "wait:0",
                "pause:4.0",
                "set:enable",
                "wait:1",
                "finish_traffic:process",
            ],
        )
        self.assertEqual(result["measurements"]["recovery_seconds"], 2.0)

    def test_restores_link_when_disable_applies_but_command_fails(self):
        class AmbiguousDisableOperations(FakeOperations):
            def set_link_state(self, state):
                super().set_link_state(state)
                if state == "disable":
                    raise RuntimeError("gnmic timeout")

        operations = AmbiguousDisableOperations()
        experiment = Experiment(
            operations,
            self.policy,
            node="leaf1",
            interface="ethernet-1/49",
            timing=self.timing,
        )

        result = experiment.run()

        self.assertEqual(result["result"], "INCONCLUSIVE")
        self.assertIn("gnmic timeout", result["error"])
        self.assertIn("set:enable", operations.events)

    def test_restore_failure_is_inconclusive(self):
        class RestoreFailureOperations(FakeOperations):
            def set_link_state(self, state):
                super().set_link_state(state)
                if state == "enable":
                    raise RuntimeError("restore failed")

        operations = RestoreFailureOperations()
        experiment = Experiment(
            operations,
            self.policy,
            node="leaf1",
            interface="ethernet-1/49",
            timing=self.timing,
        )

        result = experiment.run()

        self.assertEqual(result["result"], "INCONCLUSIVE")
        self.assertIn("restore failed", result["restore_error"])


class RetryingLabOperations(LabOperations):
    def __init__(self):
        super().__init__(
            {"preflight_attempts": 2, "preflight_interval_seconds": 0},
            maximum_telemetry_age=15,
        )
        self.attempts = 0

    def _preflight_once(self):
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("BGP is still converging")


class LabOperationsTests(unittest.TestCase):
    def test_preflight_retries_while_the_fabric_converges(self):
        operations = RetryingLabOperations()

        operations.preflight()

        self.assertEqual(operations.attempts, 2)


if __name__ == "__main__":
    unittest.main()
