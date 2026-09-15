"""Compatibility entry point for the fabric Prometheus MCP server."""

from __future__ import annotations

from mcp_servers.fabric_prometheus.server import MCPServer, main


__all__ = ["MCPServer", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
