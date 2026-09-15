"""Tiny read-only Prometheus HTTP client for MCP tools."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class PrometheusClient:
    """Read metrics from the Prometheus HTTP API."""

    def __init__(self, base_url: str = "http://localhost:9090"):
        self.base_url = base_url.rstrip("/")

    @classmethod
    def from_environment(cls) -> "PrometheusClient":
        return cls(os.environ.get("PROMETHEUS_URL", "http://localhost:9090"))

    def instant_query(self, query: str) -> list[dict[str, Any]]:
        payload = self._get("/api/v1/query", {"query": query})
        return self._results(payload)

    def range_query(
        self, query: str, *, start: str, end: str, step: str
    ) -> list[dict[str, Any]]:
        payload = self._get(
            "/api/v1/query_range",
            {"query": query, "start": start, "end": end, "step": step},
        )
        return self._results(payload)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        request = Request(f"{self.base_url}{path}?{urlencode(params)}")
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    def _results(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if payload.get("status") != "success":
            raise RuntimeError(f"Prometheus query failed: {payload}")
        return payload.get("data", {}).get("result", [])
