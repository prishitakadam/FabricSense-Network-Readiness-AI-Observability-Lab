"""Command-line entry point for the readiness experiment."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib

from .experiment import Experiment, LabOperations
from .report import write_reports


EXIT_CODES = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SR Linux fabric readiness experiment")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--config", type=Path, default=Path("readiness.toml"))
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    parser.add_argument("--maximum-error-delta", type=float)
    args = parser.parse_args(argv)

    with args.config.open("rb") as config_file:
        config = tomllib.load(config_file)
    experiment_config = config["experiment"]
    policy = dict(config["readiness"])
    if args.maximum_error_delta is not None:
        policy["maximum_error_delta"] = args.maximum_error_delta
    operations = LabOperations(experiment_config, policy["maximum_telemetry_age_seconds"])
    result = Experiment(
        operations,
        policy,
        node=experiment_config["fault_node"],
        interface=experiment_config["fault_interface"],
        timing=experiment_config,
    ).run()
    report_dir = args.output / result["experiment_id"]
    markdown_path, json_path = write_reports(result, report_dir)
    print(f"FINAL RESULT: {result['result']}")
    print(f"Markdown report: {markdown_path}")
    print(f"JSON evidence: {json_path}")
    return EXIT_CODES[result["result"]]


if __name__ == "__main__":
    sys.exit(main())
