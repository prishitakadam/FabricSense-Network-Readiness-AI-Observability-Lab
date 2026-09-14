import json
from pathlib import Path
import tempfile
import unittest

from fabric_readiness.report import write_reports


class ReportTests(unittest.TestCase):
    def test_writes_human_and_machine_readable_evidence(self):
        result = {
            "result": "PASS",
            "experiment_id": "20260913T201000Z",
            "scenario": {"node": "leaf1", "interface": "ethernet-1/49"},
            "measurements": {
                "baseline_throughput_mbps": 800.0,
                "recovered_throughput_mbps": 760.0,
                "recovery_seconds": 8.0,
            },
            "checks": [
                {
                    "name": "link_restoration",
                    "status": "PASS",
                    "observed": True,
                    "expected": "true",
                }
            ],
            "timeline": [{"event": "link_disabled", "timestamp": "2026-09-13T20:10:20Z"}],
        }

        with tempfile.TemporaryDirectory() as directory:
            markdown_path, json_path = write_reports(result, Path(directory))
            markdown = markdown_path.read_text()
            machine_result = json.loads(json_path.read_text())

        self.assertIn("# Fabric Readiness Report", markdown)
        self.assertIn("**Result: PASS**", markdown)
        self.assertIn("leaf1 / ethernet-1/49", markdown)
        self.assertIn("link_restoration | PASS", markdown)
        self.assertEqual(machine_result, result)


if __name__ == "__main__":
    unittest.main()
