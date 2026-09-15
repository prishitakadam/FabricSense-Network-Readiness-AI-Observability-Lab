import io
import json
import os
import ssl
import unittest
from unittest.mock import patch

import anyio
from mcp import Client

from mcp_servers.fabric_prometheus.fabric_investigator import FabricInvestigator
from mcp_servers.fabric_prometheus.prometheus_client import PrometheusClient
from mcp_servers.fabric_prometheus import server


class FakePrometheus:
    def __init__(self):
        self.queries = []

    def instant_query(self, query):
        self.queries.append(query)
        if query == "interface_oper_state == 0":
            return [
                {"metric": {"source": "leaf1", "interface_name": "e1-49"}, "value": [1, "0"]}
            ]
        if query == "changes(interface_oper_state[30m]) > 0":
            return [
                {"metric": {"source": "leaf1", "interface_name": "e1-49"}, "value": [1, "2"]}
            ]
        if query.startswith("topk(3,"):
            return [
                {
                    "metric": {"source": "leaf2", "interface_name": "e1-50"},
                    "value": [1, "44000000"],
                }
            ]
        if query == 'up{job="gnmic"}':
            return [{"metric": {"instance": "gnmic:9273"}, "value": [1, "1"]}]
        if "interface_statistics" in query:
            return [
                {
                    "metric": {"source": "leaf1", "interface_name": "e1-49"},
                    "value": [1, "1138"],
                }
            ]
        return []


class PrometheusClientTests(unittest.TestCase):
    def test_reads_url_from_environment(self):
        with patch.dict(os.environ, {"PROMETHEUS_URL": "http://prom.example:9090"}):
            self.assertEqual(
                PrometheusClient.from_environment().base_url,
                "http://prom.example:9090",
            )

    def test_can_skip_tls_verification_for_codespaces_forwarded_prometheus(self):
        with patch.dict(os.environ, {"PROMETHEUS_INSECURE_SKIP_VERIFY": "1"}):
            self.assertFalse(PrometheusClient.from_environment().verify_tls)

    def test_instant_query_returns_prometheus_result_list(self):
        payload = {
            "status": "success",
            "data": {
                "result": [{"metric": {"source": "leaf1"}, "value": [1, "1"]}],
            },
        }

        def fake_urlopen(request, timeout):
            return io.BytesIO(json.dumps(payload).encode())

        with patch("mcp_servers.fabric_prometheus.prometheus_client.urlopen", fake_urlopen):
            result = PrometheusClient("http://prometheus:9090").instant_query("up")

        self.assertEqual(result, payload["data"]["result"])

    def test_insecure_client_passes_unverified_ssl_context(self):
        payload = {"status": "success", "data": {"result": []}}
        captured = {}

        def fake_urlopen(request, timeout, context=None):
            captured["context"] = context
            return io.BytesIO(json.dumps(payload).encode())

        with patch("mcp_servers.fabric_prometheus.prometheus_client.urlopen", fake_urlopen):
            PrometheusClient("https://prometheus.example", verify_tls=False).instant_query("up")

        self.assertIsInstance(captured["context"], ssl.SSLContext)


class FabricInvestigatorTests(unittest.TestCase):
    def test_reports_down_links_with_evidence(self):
        result = FabricInvestigator(FakePrometheus()).down_links()

        self.assertEqual(result["query"], "interface_oper_state == 0")
        self.assertEqual(
            result["links"],
            [{"source": "leaf1", "interface_name": "e1-49", "value": 0.0}],
        )
        self.assertIn("leaf1:e1-49", result["summary"])

    def test_reports_link_changes_for_window(self):
        result = FabricInvestigator(FakePrometheus()).link_changes("30m")

        self.assertEqual(result["query"], "changes(interface_oper_state[30m]) > 0")
        self.assertEqual(result["links"][0]["changes"], 2.0)

    def test_reports_interface_errors_for_window(self):
        result = FabricInvestigator(FakePrometheus()).interface_errors("30m")

        self.assertIn("increase(interface_statistics_in_error_packets[30m])", result["query"])
        self.assertEqual(result["interfaces"][0]["errors"], 1138.0)

    def test_reports_top_traffic(self):
        result = FabricInvestigator(FakePrometheus()).top_traffic(limit=3)

        self.assertIn("topk(3,", result["query"])
        self.assertEqual(result["interfaces"][0]["mbps"], 44.0)

    def test_reports_telemetry_health(self):
        result = FabricInvestigator(FakePrometheus()).telemetry_health()

        self.assertTrue(result["healthy"])
        self.assertEqual(result["targets"][0]["value"], 1.0)


class MCPServerTests(unittest.TestCase):
    def test_fabric_tools_are_read_only_sdk_tool_functions(self):
        tool_names = {
            "fabric_down_links",
            "fabric_link_changes",
            "fabric_interface_errors",
            "fabric_top_traffic",
            "fabric_telemetry_health",
            "prometheus_instant_query",
            "prometheus_range_query",
        }

        for name in tool_names:
            self.assertTrue(callable(getattr(server, name)))

        self.assertFalse(hasattr(server, "set_link_state"))
        self.assertFalse(hasattr(server, "docker_exec"))

    def test_sdk_tool_function_queries_prometheus(self):
        with patch.object(server.PrometheusClient, "from_environment", return_value=FakePrometheus()):
            result = server.fabric_link_changes("30m")

        self.assertEqual(result["query"], "changes(interface_oper_state[30m]) > 0")

    def test_official_sdk_registers_and_calls_tools(self):
        async def run_client():
            with patch.object(server.PrometheusClient, "from_environment", return_value=FakePrometheus()):
                async with Client(server.mcp) as client:
                    tools = await client.list_tools()
                    names = {tool.name for tool in tools.tools}
                    result = await client.call_tool(
                        "fabric_link_changes", {"window": "30m"}
                    )
            return names, result.structured_content

        names, result = anyio.run(run_client)

        self.assertIn("fabric_link_changes", names)
        self.assertEqual(result["query"], "changes(interface_oper_state[30m]) > 0")


if __name__ == "__main__":
    unittest.main()
