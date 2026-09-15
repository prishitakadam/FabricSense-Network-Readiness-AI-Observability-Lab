"""Read-only fabric investigation helpers backed by Prometheus."""

from __future__ import annotations

from typing import Any


def _value(sample: dict[str, Any]) -> float:
    return float(sample["value"][1])


def _interface(sample: dict[str, Any], value_name: str) -> dict[str, Any]:
    metric = sample.get("metric", {})
    return {
        "source": metric.get("source", ""),
        "interface_name": metric.get("interface_name", ""),
        value_name: _value(sample),
    }


def _label(item: dict[str, Any]) -> str:
    return f"{item['source']}:{item['interface_name']}"


class FabricInvestigator:
    """Convert common fabric questions into safe PromQL templates."""

    def __init__(self, prometheus: Any):
        self.prometheus = prometheus

    def down_links(self) -> dict[str, Any]:
        query = "interface_oper_state == 0"
        links = [_interface(sample, "value") for sample in self.prometheus.instant_query(query)]
        summary = (
            "No monitored links are currently down."
            if not links
            else "Down links: " + ", ".join(_label(link) for link in links)
        )
        return {"query": query, "links": links, "summary": summary}

    def link_changes(self, window: str = "30m") -> dict[str, Any]:
        query = f"changes(interface_oper_state[{window}]) > 0"
        links = [_interface(sample, "changes") for sample in self.prometheus.instant_query(query)]
        summary = (
            f"No interface state changes were observed in the last {window}."
            if not links
            else f"Interfaces changed state in the last {window}: "
            + ", ".join(_label(link) for link in links)
        )
        return {"query": query, "window": window, "links": links, "summary": summary}

    def interface_errors(self, window: str = "30m") -> dict[str, Any]:
        query = (
            "sum by (source, interface_name) ("
            f"increase(interface_statistics_in_error_packets[{window}]) + "
            f"increase(interface_statistics_out_error_packets[{window}])"
            ") > 0"
        )
        interfaces = [
            _interface(sample, "errors") for sample in self.prometheus.instant_query(query)
        ]
        summary = (
            f"No interface errors increased in the last {window}."
            if not interfaces
            else f"Interfaces with errors in the last {window}: "
            + ", ".join(f"{_label(item)}={item['errors']}" for item in interfaces)
        )
        return {
            "query": query,
            "window": window,
            "interfaces": interfaces,
            "summary": summary,
        }

    def top_traffic(self, limit: int = 5) -> dict[str, Any]:
        query = f"topk({limit}, interface_traffic_rate_out_bps)"
        interfaces = [
            {
                **_interface(sample, "bps"),
                "mbps": _value(sample) / 1_000_000,
            }
            for sample in self.prometheus.instant_query(query)
        ]
        summary = (
            "No traffic-rate samples were returned."
            if not interfaces
            else "Top outbound traffic: "
            + ", ".join(f"{_label(item)}={item['mbps']:.3f} Mbps" for item in interfaces)
        )
        return {"query": query, "interfaces": interfaces, "summary": summary}

    def telemetry_health(self) -> dict[str, Any]:
        query = 'up{job="gnmic"}'
        targets = [
            {
                "instance": sample.get("metric", {}).get("instance", ""),
                "value": _value(sample),
            }
            for sample in self.prometheus.instant_query(query)
        ]
        healthy = bool(targets) and all(target["value"] == 1.0 for target in targets)
        summary = "gNMIc telemetry scrape is healthy." if healthy else "gNMIc telemetry scrape is unhealthy."
        return {"query": query, "healthy": healthy, "targets": targets, "summary": summary}
