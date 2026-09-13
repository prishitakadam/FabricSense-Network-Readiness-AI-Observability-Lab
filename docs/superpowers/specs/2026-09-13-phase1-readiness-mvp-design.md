# Phase 1 Fabric Readiness MVP Design

## Goal

Extend the Nokia SR Linux Telemetry Lab with one repeatable experiment that validates a healthy fabric, benchmarks `client2` to `client1`, disables `leaf1` interface `ethernet-1/49`, measures impact and recovery, restores the link, and emits Markdown and JSON readiness reports.

## Scope

Phase 1 reuses the upstream three-leaf/two-spine EVPN topology, gNMIc collector, Prometheus configuration, and Grafana dashboard. Loki and Alloy are excluded. The only supported scenario is a single leaf-to-spine link failure during TCP `iperf3` traffic.

## Architecture

Containerlab deploys all network, client, and observability containers in GitHub Codespaces. A Python 3.11 standard-library runner shells out to Docker for endpoint traffic and to gNMIc for interface configuration, and queries the Prometheus HTTP API for evidence. Pure functions parse `iperf3` output and classify the result; orchestration always restores the link in a `finally` block.

## Workflow

1. Confirm required containers, endpoint reachability, selected-link state, Prometheus health, and telemetry freshness.
2. Run a short baseline benchmark and record throughput and retransmissions.
3. Run fault-window traffic, disable the selected link, confirm telemetry observes the fault, then restore the link.
4. Confirm link and traffic recovery, calculate readiness checks, and retain raw evidence.
5. Write `report.md` and `results.json`; exit 0 for PASS, 1 for FAIL, or 2 for INCONCLUSIVE.

## Readiness Rules

Thresholds live in `readiness.toml`. PASS requires trustworthy preflight evidence, a successful baseline, observed link failure, recovered traffic within the limit, recovered throughput at or above the configured baseline ratio, and successful link restoration. FAIL means a valid experiment violated a readiness threshold. INCONCLUSIVE means tooling, telemetry, or initial-health problems prevented a trustworthy experiment.

## Constraints

- Runtime platform: GitHub Codespaces/Linux with Docker and Containerlab.
- Python: 3.11 or newer, standard library only.
- Fault target: `leaf1` / `ethernet-1/49` for the MVP.
- Traffic pair: `client2` to the `iperf3` server on `client1`.
- All upstream-derived files retain their BSD-3-Clause headers and attribution.
- Phase 2 features are not implemented.

## Verification

Unit tests cover `iperf3` parsing, Prometheus value parsing, readiness classification, and report generation. Static configuration checks run without Docker. The Codespaces smoke test deploys the lab and runs `make experiment`, verifies the report and exit code, and confirms the faulted link is restored.
