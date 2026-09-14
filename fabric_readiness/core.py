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
            "intervals": [
                {
                    "start": float(interval["sum"]["start"]),
                    "end": float(interval["sum"]["end"]),
                    "throughput_mbps": interval["sum"]["bits_per_second"] / 1_000_000,
                }
                for interval in intervals
            ],
        }
    except IperfError:
        raise
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise IperfError(f"invalid iperf3 JSON: {error}") from error


def analyze_fault_intervals(
    intervals: list[dict[str, float]],
    *,
    baseline_mbps: float,
    fault_offset: float,
    restore_offset: float,
    minimum_degraded_ratio: float,
    sustained_intervals: int = 2,
) -> dict[str, Any]:
    """Measure traffic interruption and recovery from one continuous iperf run."""
    threshold = baseline_mbps * minimum_degraded_ratio
    fault_intervals = [interval for interval in intervals if interval["end"] > fault_offset]

    recovery_start: float | None = None
    for index, interval in enumerate(fault_intervals):
        window = fault_intervals[index : index + sustained_intervals]
        if len(window) == sustained_intervals and all(
            item["throughput_mbps"] >= threshold for item in window
        ):
            recovery_start = max(interval["start"], fault_offset)
            break

    traffic_recovered = recovery_start is not None
    end_offset = intervals[-1]["end"] if intervals else fault_offset
    maximum_interruption_seconds = (
        recovery_start - fault_offset if recovery_start is not None else end_offset - fault_offset
    )

    degraded_start = recovery_start if recovery_start is not None else fault_offset
    degraded = [
        interval["throughput_mbps"]
        for interval in intervals
        if interval["start"] >= degraded_start and interval["start"] < restore_offset
    ]
    recovered = [
        interval["throughput_mbps"]
        for interval in intervals
        if interval["start"] >= restore_offset
    ]

    return {
        "traffic_recovered": traffic_recovered,
        "recovery_seconds": maximum_interruption_seconds if traffic_recovered else None,
        "maximum_interruption_seconds": maximum_interruption_seconds,
        "degraded_throughput_mbps": sum(degraded) / len(degraded) if degraded else 0.0,
        "recovered_throughput_mbps": sum(recovered) / len(recovered) if recovered else 0.0,
    }


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
    add("traffic_recovered", evidence["traffic_recovered"], evidence["traffic_recovered"], "true")

    baseline = float(evidence["baseline_throughput_mbps"])
    add(
        "baseline_throughput",
        baseline >= policy["minimum_baseline_mbps"],
        baseline,
        f">= {policy['minimum_baseline_mbps']} Mbps",
    )
    degraded = float(evidence["degraded_throughput_mbps"])
    degraded_ratio = degraded / baseline if baseline > 0 else 0.0
    add(
        "degraded_throughput",
        degraded_ratio >= policy["minimum_degraded_ratio"],
        round(degraded_ratio, 4),
        f">= {policy['minimum_degraded_ratio']} of baseline",
    )
    add("link_restoration", evidence["restored"], evidence["restored"], "true")

    recovery_seconds = evidence["recovery_seconds"]
    add(
        "recovery_time",
        recovery_seconds is not None and float(recovery_seconds) <= policy["maximum_recovery_seconds"],
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
