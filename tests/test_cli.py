from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fabric_readiness import __main__


CONFIG = b"""
[experiment]
source_container = "client2"
destination_address = "172.17.0.1"
fault_node = "leaf1"
fault_interface = "ethernet-1/49"
prometheus_url = "http://localhost:9090"
benchmark_seconds = 15
parallel_streams = 8

[readiness]
minimum_baseline_mbps = 20.0
minimum_degraded_ratio = 0.70
minimum_recovered_ratio = 0.90
maximum_recovery_seconds = 30.0
maximum_telemetry_age_seconds = 15.0
maximum_error_delta = 0.0
"""


class CliTests(unittest.TestCase):
    def run_cli(self, *extra_args):
        captured = {}

        class FakeExperiment:
            def __init__(self, operations, policy, *, node, interface, timing):
                captured["policy"] = policy

            def run(self):
                return {
                    "experiment_id": "20260914T000000Z",
                    "result": "PASS",
                    "scenario": {"node": "leaf1", "interface": "ethernet-1/49"},
                    "measurements": {},
                    "checks": [],
                    "timeline": [],
                }

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "readiness.toml"
            config_path.write_bytes(CONFIG)
            with (
                patch("fabric_readiness.__main__.LabOperations"),
                patch("fabric_readiness.__main__.Experiment", FakeExperiment),
                patch(
                    "fabric_readiness.__main__.write_reports",
                    return_value=(Path("report.md"), Path("results.json")),
                ),
            ):
                exit_code = __main__.main(
                    ["run", "--config", str(config_path), "--output", directory, *extra_args]
                )

        return exit_code, captured["policy"]

    def test_uses_configured_error_delta_by_default(self):
        exit_code, policy = self.run_cli()

        self.assertEqual(exit_code, 0)
        self.assertEqual(policy["maximum_error_delta"], 0.0)

    def test_can_override_maximum_error_delta(self):
        exit_code, policy = self.run_cli("--maximum-error-delta", "2000")

        self.assertEqual(exit_code, 0)
        self.assertEqual(policy["maximum_error_delta"], 2000.0)
        self.assertEqual(policy["minimum_baseline_mbps"], 20.0)


if __name__ == "__main__":
    unittest.main()
