"""Experiment orchestration and real lab operations."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from .core import analyze_fault_intervals, evaluate, parse_iperf, parse_prometheus_value


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
        self.evidence: dict[str, Any] = {"prometheus_queries": [], "gnmi_operations": []}

    def _run(self, command: list[str], timeout: int = 60) -> str:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return completed.stdout

    def run_checked(self, command: list[str], timeout: int = 60) -> str:
        try:
            return self._run(command, timeout=timeout)
        except subprocess.CalledProcessError as error:
            details = (error.stderr or error.stdout or str(error)).strip()
            raise RuntimeError(
                f"{' '.join(command)} failed with exit {error.returncode}: {details}"
            ) from error

    def _query(self, expression: str) -> float:
        query = urlencode({"query": expression})
        with urlopen(f"{self.config['prometheus_url']}/api/v1/query?{query}", timeout=10) as response:
            payload = json.load(response)
        value = parse_prometheus_value(payload)
        self.evidence["prometheus_queries"].append(
            {"timestamp": timestamp(), "expression": expression, "value": value, "raw": payload}
        )
        return value

    def _selector(self) -> str:
        short_interface = self.config["fault_interface"].replace("ethernet-", "e").replace("/", "-")
        return f'source="{self.config["fault_node"]}",interface_name="{short_interface}"'

    def preflight(self) -> None:
        attempts = int(self.config.get("preflight_attempts", 1))
        interval = float(self.config.get("preflight_interval_seconds", 5))
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                self._preflight_once()
                return
            except (RuntimeError, subprocess.SubprocessError, OSError, ValueError) as error:
                last_error = error
                if attempt + 1 < attempts:
                    time.sleep(interval)
        raise RuntimeError(f"lab did not become ready: {last_error}")

    def _preflight_once(self) -> None:
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

    def start_fault_benchmark(self, seconds: int) -> subprocess.Popen[str]:
        return subprocess.Popen(
            [
                "docker", "exec", self.config["source_container"], "iperf3",
                "-c", self.config["destination_address"],
                "-P", str(self.config["parallel_streams"]),
                "-t", str(seconds), "-i", "1", "--json",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def finish_fault_benchmark(self, process: subprocess.Popen[str]) -> dict[str, Any]:
        seconds = int(self.config.get("fault_traffic_seconds", self.config["benchmark_seconds"]))
        try:
            stdout, stderr = process.communicate(timeout=seconds + 30)
        except subprocess.TimeoutExpired:
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            raise RuntimeError("iperf3 fault benchmark timed out")
        if process.returncode:
            raise RuntimeError(stderr.strip() or f"iperf3 exited with {process.returncode}")
        return parse_iperf(stdout)

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
        command = [
            "docker", "exec", "gnmic", "/app/gnmic",
            "-a", f"{self.config['fault_node']}:57400",
            "-u", "admin", "-p", "NokiaSrl1!", "--skip-verify",
            "set",
            "--update-path", f"/interface[name={self.config['fault_interface']}]/admin-state",
            "--update-value", state,
        ]
        record = {"timestamp": timestamp(), "state": state}
        try:
            record["output"] = self.run_checked(command, timeout=20)
            self.evidence["gnmi_operations"].append(record)
        except Exception as error:
            record["error"] = f"{type(error).__name__}: {error}"
            self.evidence["gnmi_operations"].append(record)
            raise

    def wait_link_state(self, expected: int) -> bool:
        deadline = time.monotonic() + float(self.config["state_timeout_seconds"])
        while time.monotonic() < deadline:
            if self.link_state() == expected:
                return True
            time.sleep(1)
        return False

    def pause(self, seconds: float) -> None:
        time.sleep(seconds)

    def monotonic(self) -> float:
        return time.monotonic()


class Experiment:
    """Run one controlled leaf-to-spine failure and always clean it up."""

    def __init__(
        self,
        operations: Any,
        policy: dict[str, float],
        *,
        node: str,
        interface: str,
        timing: dict[str, Any] | None = None,
    ):
        self.operations = operations
        self.policy = policy
        self.node = node
        self.interface = interface
        self.timing = timing or {}

    def run(self) -> dict[str, Any]:
        experiment_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        result: dict[str, Any] = {
            "experiment_id": experiment_id,
            "scenario": {"node": self.node, "interface": self.interface},
            "timeline": [{"event": "experiment_started", "timestamp": timestamp()}],
        }
        cleanup_required = False
        restored = False
        traffic_process: Any = None
        fault_offset = 0.0
        restore_offset = 0.0

        try:
            self.operations.preflight()
            result["timeline"].append({"event": "preflight_passed", "timestamp": timestamp()})
            baseline = self.operations.benchmark()
            errors_before = self.operations.error_count()
            telemetry_fresh = self.operations.telemetry_is_fresh()

            pre_fault_seconds = float(self.timing.get("pre_fault_seconds", 5))
            fault_hold_seconds = float(self.timing.get("fault_hold_seconds", 10))
            fault_traffic_seconds = int(self.timing.get("fault_traffic_seconds", 70))
            traffic_process = self.operations.start_fault_benchmark(fault_traffic_seconds)
            traffic_started = self.operations.monotonic()
            result["timeline"].append({"event": "traffic_started", "timestamp": timestamp()})
            self.operations.pause(pre_fault_seconds)

            cleanup_required = True
            fault_offset = self.operations.monotonic() - traffic_started
            self.operations.set_link_state("disable")
            result["timeline"].append({"event": "link_disabled", "timestamp": timestamp()})
            fault_observed = self.operations.wait_link_state(0)
            self.operations.pause(fault_hold_seconds)
        except Exception as error:
            result["error"] = f"{type(error).__name__}: {error}"
        finally:
            if cleanup_required:
                try:
                    self.operations.set_link_state("enable")
                    restore_offset = self.operations.monotonic() - traffic_started
                    restored = self.operations.wait_link_state(1)
                    result["timeline"].append({"event": "link_restore_attempted", "timestamp": timestamp()})
                except Exception as restore_error:
                    result["restore_error"] = f"{type(restore_error).__name__}: {restore_error}"

        fault_benchmark = None
        if traffic_process is not None:
            try:
                fault_benchmark = self.operations.finish_fault_benchmark(traffic_process)
            except Exception as error:
                result.setdefault("error", f"{type(error).__name__}: {error}")

        if "error" in result:
            result.update(
                {
                    "result": "INCONCLUSIVE",
                    "measurements": {"restored": restored},
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
            result["evidence"] = self._operation_evidence(baseline=locals().get("baseline"), fault=fault_benchmark)
            result["timeline"].append({"event": "experiment_finished", "timestamp": timestamp()})
            return result

        if "restore_error" in result:
            result.update(
                {
                    "result": "INCONCLUSIVE",
                    "measurements": {"restored": restored},
                    "checks": [
                        {
                            "name": "link_restoration",
                            "status": "INCONCLUSIVE",
                            "observed": result["restore_error"],
                            "expected": "link restored after fault injection",
                        }
                    ],
                }
            )
            result["evidence"] = self._operation_evidence(baseline=baseline, fault=fault_benchmark)
            result["timeline"].append({"event": "experiment_finished", "timestamp": timestamp()})
            return result

        try:
            if fault_benchmark is None:
                raise RuntimeError("fault benchmark did not produce evidence")
            traffic = analyze_fault_intervals(
                fault_benchmark["intervals"],
                baseline_mbps=baseline["throughput_mbps"],
                fault_offset=fault_offset,
                restore_offset=restore_offset,
                minimum_degraded_ratio=self.policy["minimum_degraded_ratio"],
                sustained_intervals=int(self.timing.get("sustained_recovery_intervals", 2)),
            )
            errors_after = self.operations.error_count()
            evidence = {
                "preflight_ok": True,
                "telemetry_fresh": telemetry_fresh and self.operations.telemetry_is_fresh(),
                "fault_observed": fault_observed,
                "restored": restored,
                "traffic_recovered": traffic["traffic_recovered"],
                "baseline_throughput_mbps": baseline["throughput_mbps"],
                "degraded_throughput_mbps": traffic["degraded_throughput_mbps"],
                "recovered_throughput_mbps": traffic["recovered_throughput_mbps"],
                "recovery_seconds": traffic["recovery_seconds"],
                "error_delta": max(0.0, errors_after - errors_before),
            }
            readiness, checks = evaluate(evidence, self.policy)
            result.update(
                {
                    "result": readiness,
                    "checks": checks,
                    "measurements": {
                        "baseline_throughput_mbps": round(baseline["throughput_mbps"], 3),
                        "degraded_throughput_mbps": round(traffic["degraded_throughput_mbps"], 3),
                        "recovered_throughput_mbps": round(traffic["recovered_throughput_mbps"], 3),
                        "recovery_seconds": round(traffic["recovery_seconds"], 3)
                        if traffic["recovery_seconds"] is not None else None,
                        "maximum_interruption_seconds": round(
                            traffic["maximum_interruption_seconds"], 3
                        ),
                        "baseline_retransmits": baseline["retransmits"],
                        "fault_window_retransmits": fault_benchmark["retransmits"],
                        "interface_error_delta": evidence["error_delta"],
                    },
                    "evidence": self._operation_evidence(baseline=baseline, fault=fault_benchmark),
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
            result["evidence"] = self._operation_evidence(baseline=locals().get("baseline"), fault=fault_benchmark)
        result["timeline"].append({"event": "experiment_finished", "timestamp": timestamp()})
        return result

    def _operation_evidence(
        self, *, baseline: dict[str, Any] | None, fault: dict[str, Any] | None
    ) -> dict[str, Any]:
        return {
            "operations": getattr(self.operations, "evidence", {}),
            "benchmarks": {
                "baseline": baseline,
                "fault_window": fault,
            },
        }
