"""Pure parsing and readiness-evaluation functions."""

from __future__ import annotations

import json
from typing import Any


class IperfError(ValueError):
    """Raised when iperf3 did not produce a usable benchmark."""


def parse_iperf(payload: str) -> dict[str, Any]:
    """Return the measurements used by the readiness policy."""
    try:
        document = json.loads(payload)
        if document.get("error"):
            raise IperfError(document["error"])
        end = document["end"]
        receiver = end.get("sum_received") or end["sum"]
        sender = end.get("sum_sent", {})
        intervals = document.get("intervals", [])
        return {
            "throughput_mbps": receiver["bits_per_second"] / 1_000_000,
            "retransmits": int(sender.get("retransmits", 0)),
            "intervals_mbps": [
                interval["sum"]["bits_per_second"] / 1_000_000
                for interval in intervals
            ],
        }
    except IperfError:
        raise
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise IperfError(f"invalid iperf3 JSON: {error}") from error


def parse_prometheus_value(payload: dict[str, Any]) -> float:
    """Extract one numeric value from a Prometheus instant-query response."""
    if payload.get("status") != "success":
        raise ValueError("Prometheus query was not successful")
    results = payload.get("data", {}).get("result", [])
    if len(results) != 1:
        raise ValueError("Prometheus query must return exactly one result")
    try:
        return float(results[0]["value"][1])
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ValueError("Prometheus result has no numeric value") from error


def evaluate(
    evidence: dict[str, Any], policy: dict[str, float]
) -> tuple[str, list[dict[str, Any]]]:
    """Apply explicit readiness rules to collected evidence."""
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: str, *, trust=False):
        checks.append(
            {
                "name": name,
                "status": "PASS" if passed else ("INCONCLUSIVE" if trust else "FAIL"),
                "observed": observed,
                "expected": expected,
            }
        )

    add("initial_health", evidence["preflight_ok"], evidence["preflight_ok"], "true", trust=True)
    add(
        "telemetry_freshness",
        evidence["telemetry_fresh"],
        evidence["telemetry_fresh"],
        "true",
        trust=True,
    )
    add("fault_observed", evidence["fault_observed"], evidence["fault_observed"], "true", trust=True)

    baseline = float(evidence["baseline_throughput_mbps"])
    add(
        "baseline_throughput",
        baseline >= policy["minimum_baseline_mbps"],
        baseline,
        f">= {policy['minimum_baseline_mbps']} Mbps",
    )
    add("link_restoration", evidence["restored"], evidence["restored"], "true")

    recovery_seconds = float(evidence["recovery_seconds"])
    add(
        "recovery_time",
        recovery_seconds <= policy["maximum_recovery_seconds"],
        recovery_seconds,
        f"<= {policy['maximum_recovery_seconds']} seconds",
    )

    recovered = float(evidence["recovered_throughput_mbps"])
    ratio = recovered / baseline if baseline > 0 else 0.0
    add(
        "recovered_throughput",
        ratio >= policy["minimum_recovered_ratio"],
        round(ratio, 4),
        f">= {policy['minimum_recovered_ratio']} of baseline",
    )

    error_delta = float(evidence["error_delta"])
    add(
        "interface_errors",
        error_delta <= policy["maximum_error_delta"],
        error_delta,
        f"<= {policy['maximum_error_delta']}",
    )

    statuses = {check["status"] for check in checks}
    if "INCONCLUSIVE" in statuses:
        return "INCONCLUSIVE", checks
    if "FAIL" in statuses:
        return "FAIL", checks
    return "PASS", checks
