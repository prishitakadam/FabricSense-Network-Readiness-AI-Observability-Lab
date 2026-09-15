"""Read-only MCP server exposing Prometheus-backed fabric investigation tools."""

from __future__ import annotations

import json
import sys
from typing import Any

from .fabric_investigator import FabricInvestigator
from .prometheus_client import PrometheusClient


class MCPServer:
    """Minimal stdio MCP server for read-only fabric telemetry."""

    def __init__(self, prometheus: Any | None = None):
        self.prometheus = prometheus or PrometheusClient.from_environment()
        self.investigator = FabricInvestigator(self.prometheus)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            self._tool("fabric_down_links", "List interfaces currently down.", {}),
            self._tool(
                "fabric_link_changes",
                "List interfaces whose operational state changed in a time window.",
                {"window": {"type": "string", "default": "30m"}},
            ),
            self._tool(
                "fabric_interface_errors",
                "List interfaces with increased error counters in a time window.",
                {"window": {"type": "string", "default": "30m"}},
            ),
            self._tool(
                "fabric_top_traffic",
                "List interfaces with the highest outbound traffic rate.",
                {"limit": {"type": "integer", "default": 5}},
            ),
            self._tool("fabric_telemetry_health", "Check Prometheus scraping of gNMIc.", {}),
            self._tool(
                "prometheus_instant_query",
                "Run a read-only Prometheus instant query.",
                {"query": {"type": "string"}},
                required=["query"],
            ),
            self._tool(
                "prometheus_range_query",
                "Run a read-only Prometheus range query.",
                {
                    "query": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "step": {"type": "string"},
                },
                required=["query", "start", "end", "step"],
            ),
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        if name == "fabric_down_links":
            return self.investigator.down_links()
        if name == "fabric_link_changes":
            return self.investigator.link_changes(arguments.get("window", "30m"))
        if name == "fabric_interface_errors":
            return self.investigator.interface_errors(arguments.get("window", "30m"))
        if name == "fabric_top_traffic":
            return self.investigator.top_traffic(int(arguments.get("limit", 5)))
        if name == "fabric_telemetry_health":
            return self.investigator.telemetry_health()
        if name == "prometheus_instant_query":
            query = arguments["query"]
            return {"query": query, "result": self.prometheus.instant_query(query)}
        if name == "prometheus_range_query":
            query = arguments["query"]
            return {
                "query": query,
                "result": self.prometheus.range_query(
                    query,
                    start=arguments["start"],
                    end=arguments["end"],
                    step=arguments["step"],
                ),
            }
        raise ValueError(f"unknown MCP tool: {name}")

    def serve(self) -> None:
        for line in sys.stdin:
            if not line.strip():
                continue
            response = self.handle(json.loads(line))
            if response is not None:
                print(json.dumps(response), flush=True)

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        if "id" not in request:
            return None
        try:
            result = self._handle_method(request.get("method"), request.get("params", {}))
            return {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except Exception as error:
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {"code": -32000, "message": str(error)},
            }

    def _handle_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "srl-fabric-prometheus",
                    "version": "0.1.0",
                },
            }
        if method == "tools/list":
            return {"tools": self.list_tools()}
        if method == "tools/call":
            result = self.call_tool(params["name"], params.get("arguments", {}))
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2, sort_keys=True),
                    }
                ]
            }
        raise ValueError(f"unsupported MCP method: {method}")

    def _tool(
        self,
        name: str,
        description: str,
        properties: dict[str, Any],
        *,
        required: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        }


def main() -> int:
    MCPServer().serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
