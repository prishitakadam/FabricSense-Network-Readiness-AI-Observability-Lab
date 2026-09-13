from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LabConfigurationTests(unittest.TestCase):
    def test_phase1_topology_has_required_nodes_without_phase2_logging(self):
        topology = (ROOT / "st.clab.yml").read_text()

        for node in (
            "spine1:", "spine2:", "leaf1:", "leaf2:", "leaf3:",
            "client1:", "client2:", "client3:", "gnmic:",
            "prometheus:", "grafana:",
        ):
            self.assertIn(node, topology)
        self.assertNotIn("    loki:", topology)
        self.assertNotIn("    alloy:", topology)

    def test_grafana_uses_only_prometheus_in_phase1(self):
        datasource = (ROOT / "configs/grafana/datasource.yml").read_text()

        self.assertIn("url: http://prometheus:9090", datasource)
        self.assertNotIn("type: loki", datasource)


if __name__ == "__main__":
    unittest.main()
