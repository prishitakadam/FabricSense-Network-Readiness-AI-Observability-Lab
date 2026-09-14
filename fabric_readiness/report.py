"""Write readiness evidence for humans and automation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_reports(result: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    """Write report.md and results.json into an experiment directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "report.md"
    json_path = output_dir / "results.json"

    scenario = result["scenario"]
    measurements = result.get("measurements", {})
    lines = [
        "# Fabric Readiness Report",
        "",
        f"**Result: {result['result']}**",
        "",
        f"- Experiment: `{result['experiment_id']}`",
        f"- Fault: `{scenario['node']} / {scenario['interface']}`",
        "",
        "## Measurements",
        "",
    ]
    if measurements:
        lines.extend(
            f"- {name.replace('_', ' ').title()}: `{value}`"
            for name, value in measurements.items()
        )
    else:
        lines.append("- No trustworthy measurements were collected.")

    lines.extend(["", "## Readiness Checks", "", "Check | Status | Observed | Expected", "--- | --- | --- | ---"])
    lines.extend(
        f"{check['name']} | {check['status']} | {check['observed']} | {check['expected']}"
        for check in result.get("checks", [])
    )
    lines.extend(["", "## Timeline", ""])
    lines.extend(
        f"- `{entry['timestamp']}` — {entry['event']}"
        for entry in result.get("timeline", [])
    )
    if result.get("error"):
        lines.extend(["", "## Experiment Error", "", result["error"]])

    markdown_path.write_text("\n".join(lines) + "\n")
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return markdown_path, json_path
