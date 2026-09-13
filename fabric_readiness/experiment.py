"""Experiment orchestration and real lab operations."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from .core import evaluate, parse_iperf, parse_prometheus_value


REQUIRED_CONTAINERS = (
    "spine1", "spine2", "leaf1", "leaf2", "leaf3",
    "client1", "client2", "client3", "gnmic", "prometheus", "grafana",
)


def timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class LabOperations:
    """Boundary around Docker, gNMIc, iperf3, and Prometheus."""

    def __init__(self, config: dict[str, Any], maximum_telemetry_age: float):
        self.config = config
        self.maximum_telemetry_age = maximum_telemetry_age

    def _run(self, command: list[str], timeout: int = 60) -> str:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return completed.stdout

    def _query(self, expression: str) -> float:
        query = urlencode({"query": expression})
        with urlopen(f"{self.config['prometheus_url']}/api/v1/query?{query}", timeout=10) as response:
            return parse_prometheus_value(json.load(response))

    def _selector(self) -> str:
        short_interface = self.config["fault_interface"].replace("ethernet-", "e").replace("/", "-")
        return f'source="{self.config["fault_node"]}",interface_name="{short_interface}"'

    def preflight(self) -> None:
        for container in REQUIRED_CONTAINERS:
            running = self._run(["docker", "inspect", "-f", "{{.State.Running}}", container]).strip()
            if running != "true":
                raise RuntimeError(f"required container is not running: {container}")
        self._run(
            [
                "docker", "exec", self.config["source_container"],
                "ping", "-c", "3", "-W", "2", self.config["destination_address"],
            ],
            timeout=15,
        )
        if self._query('up{job="gnmic"}') != 1:
            raise RuntimeError("Prometheus cannot scrape gNMIc")
        if self.link_state() != 1:
            raise RuntimeError("selected fault interface is not initially up")
        if not self.telemetry_is_fresh():
            raise RuntimeError("selected interface telemetry is stale")

    def benchmark(self) -> dict[str, Any]:
        seconds = int(self.config["benchmark_seconds"])
        output = self._run(
            [
                "docker", "exec", self.config["source_container"], "iperf3",
                "-c", self.config["destination_address"],
                "-P", str(self.config["parallel_streams"]),
                "-t", str(seconds), "-i", "1", "--json",
            ],
            timeout=seconds + 20,
        )
        return parse_iperf(output)

    def link_state(self) -> float:
        return self._query(f"interface_oper_state{{{self._selector()}}}")

    def telemetry_is_fresh(self) -> bool:
        age = self._query(f"time() - timestamp(interface_oper_state{{{self._selector()}}})")
        return age <= self.maximum_telemetry_age

    def error_count(self) -> float:
        selector = self._selector()
        expression = (
            'sum({__name__=~"interface_statistics_(in|out)_error_packets",'
            f"{selector}}}) or vector(0)"
        )
        return self._query(expression)

    def set_link_state(self, state: str) -> None:
        self._run(
            [
                "docker", "exec", "gnmic", "gnmic",
                "-a", f"{self.config['fault_node']}:57400",
                "-u", "admin", "-p", "NokiaSrl1!", "--skip-verify",
                "set",
                "--update-path", f"/interface[name={self.config['fault_interface']}]/admin-state",
                "--update-value", state,
            ],
            timeout=20,
        )

    def wait_link_state(self, expected: int) -> bool:
        deadline = time.monotonic() + float(self.config["state_timeout_seconds"])
        while time.monotonic() < deadline:
            if self.link_state() == expected:
                return True
            time.sleep(1)
        return False


class Experiment:
    """Run one controlled leaf-to-spine failure and always clean it up."""

    def __init__(self, operations: Any, policy: dict[str, float], *, node: str, interface: str):
        self.operations = operations
        self.policy = policy
        self.node = node
        self.interface = interface

    def run(self) -> dict[str, Any]:
        experiment_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        result: dict[str, Any] = {
            "experiment_id": experiment_id,
            "scenario": {"node": self.node, "interface": self.interface},
            "timeline": [{"event": "experiment_started", "timestamp": timestamp()}],
        }
        disabled = False
        restored = False
        restore_started = 0.0

        try:
            self.operations.preflight()
            result["timeline"].append({"event": "preflight_passed", "timestamp": timestamp()})
            baseline = self.operations.benchmark()
            errors_before = self.operations.error_count()
            telemetry_fresh = self.operations.telemetry_is_fresh()

            self.operations.set_link_state("disable")
            disabled = True
            result["timeline"].append({"event": "link_disabled", "timestamp": timestamp()})
            fault_observed = self.operations.wait_link_state(0)
            degraded = self.operations.benchmark()
        except Exception as error:
            result["error"] = f"{type(error).__name__}: {error}"
        finally:
            if disabled:
                restore_started = time.monotonic()
                try:
                    self.operations.set_link_state("enable")
                    restored = self.operations.wait_link_state(1)
                    result["timeline"].append({"event": "link_restore_attempted", "timestamp": timestamp()})
                except Exception as restore_error:
                    result["restore_error"] = f"{type(restore_error).__name__}: {restore_error}"

        if "error" in result:
            result.update(
                {
                    "result": "INCONCLUSIVE",
                    "measurements": {},
                    "checks": [
                        {
                            "name": "experiment_execution",
                            "status": "INCONCLUSIVE",
                            "observed": result["error"],
                            "expected": "experiment completes with trustworthy evidence",
                        },
                        {
                            "name": "link_restoration",
                            "status": "PASS" if restored else "INCONCLUSIVE",
                            "observed": restored,
                            "expected": "true",
                        },
                    ],
                }
            )
            return result

        recovery_seconds = time.monotonic() - restore_started
        try:
            recovered = self.operations.benchmark()
            errors_after = self.operations.error_count()
            evidence = {
                "preflight_ok": True,
                "telemetry_fresh": telemetry_fresh and self.operations.telemetry_is_fresh(),
                "fault_observed": fault_observed,
                "restored": restored,
                "baseline_throughput_mbps": baseline["throughput_mbps"],
                "degraded_throughput_mbps": degraded["throughput_mbps"],
                "recovered_throughput_mbps": recovered["throughput_mbps"],
                "recovery_seconds": recovery_seconds,
                "error_delta": max(0.0, errors_after - errors_before),
            }
            readiness, checks = evaluate(evidence, self.policy)
            result.update(
                {
                    "result": readiness,
                    "checks": checks,
                    "measurements": {
                        "baseline_throughput_mbps": round(baseline["throughput_mbps"], 3),
                        "degraded_throughput_mbps": round(degraded["throughput_mbps"], 3),
                        "recovered_throughput_mbps": round(recovered["throughput_mbps"], 3),
                        "recovery_seconds": round(recovery_seconds, 3),
                        "baseline_retransmits": baseline["retransmits"],
                        "degraded_retransmits": degraded["retransmits"],
                        "recovered_retransmits": recovered["retransmits"],
                        "interface_error_delta": evidence["error_delta"],
                    },
                }
            )
        except Exception as error:
            result.update(
                {
                    "result": "INCONCLUSIVE",
                    "error": f"{type(error).__name__}: {error}",
                    "measurements": {},
                    "checks": [
                        {
                            "name": "recovery_measurement",
                            "status": "INCONCLUSIVE",
                            "observed": str(error),
                            "expected": "valid recovery benchmark and telemetry",
                        }
                    ],
                }
            )
        result["timeline"].append({"event": "experiment_finished", "timestamp": timestamp()})
        return result
