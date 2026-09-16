"""Official MCP SDK server for read-only Prometheus fabric investigation."""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from .fabric_investigator import FabricInvestigator
from .prometheus_client import PrometheusClient


mcp = MCPServer(
    "srl-fabric-prometheus",
    instructions=(
        "Read-only tools for investigating SR Linux fabric telemetry from Prometheus. "
        "Do not claim readiness PASS/FAIL unless that result is exported as a metric."
    ),
)


def _investigator() -> FabricInvestigator:
    return FabricInvestigator(PrometheusClient.from_environment())


def _prometheus() -> PrometheusClient:
    return PrometheusClient.from_environment()


@mcp.tool()
def fabric_down_links() -> dict[str, Any]:
    """List monitored interfaces that are currently down."""
    return _investigator().down_links()


@mcp.tool()
def fabric_link_changes(window: str = "30m") -> dict[str, Any]:
    """List interfaces whose operational state changed in the time window."""
    return _investigator().link_changes(window)


@mcp.tool()
def fabric_interface_errors(window: str = "30m") -> dict[str, Any]:
    """List interfaces with increased in/out error counters in the time window."""
    return _investigator().interface_errors(window)


@mcp.tool()
def fabric_top_traffic(limit: int = 5) -> dict[str, Any]:
    """List interfaces with the highest outbound traffic rate."""
    return _investigator().top_traffic(limit)


@mcp.tool()
def fabric_telemetry_health() -> dict[str, Any]:
    """Check whether Prometheus is successfully scraping gNMIc."""
    return _investigator().telemetry_health()


@mcp.tool()
def prometheus_instant_query(query: str) -> dict[str, Any]:
    """Run a read-only Prometheus instant query."""
    return {"query": query, "result": _prometheus().instant_query(query)}


@mcp.tool()
def prometheus_range_query(query: str, start: str, end: str, step: str) -> dict[str, Any]:
    """Run a read-only Prometheus range query."""
    return {
        "query": query,
        "result": _prometheus().range_query(query, start=start, end=end, step=step),
    }


def main() -> int:
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
