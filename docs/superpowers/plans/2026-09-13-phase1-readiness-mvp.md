# Phase 1 Fabric Readiness MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a one-command SR Linux link-failure readiness experiment with Prometheus evidence and Markdown/JSON results.

**Architecture:** Reuse the upstream Containerlab topology and telemetry assets. Add a Python standard-library runner whose external command boundary is injectable while parsing, classification, and reporting stay pure and unit-testable.

**Tech Stack:** Containerlab, Nokia SR Linux, Docker, gNMIc, Prometheus, Grafana, iperf3, Python 3.11, unittest, Make.

**Spec:** `docs/superpowers/specs/2026-09-13-phase1-readiness-mvp-design.md`

## Global Constraints

- Runtime platform: GitHub Codespaces/Linux with Docker and Containerlab.
- Python 3.11 or newer, standard library only.
- Fault target: `leaf1` / `ethernet-1/49` for the MVP.
- Traffic pair: `client2` to the `iperf3` server on `client1`.
- All upstream-derived files retain their BSD-3-Clause headers and attribution.
- Phase 2 features are not implemented.

---

### Task 1: Import the Phase 1 lab

**Files:**
- Create: `st.clab.yml`
- Create: `configs/fabric/*.cfg`
- Create: `configs/client2/iperf.sh`
- Create: `configs/client3/iperf.sh`
- Create: `configs/gnmic/gnmic-config.yml`
- Create: `configs/prometheus/prometheus.yml`
- Create: `configs/grafana/**`

**Interfaces:**
- Consumes: upstream `srl-labs/srl-telemetry-lab` at the downloaded revision.
- Produces: a Containerlab topology without Loki or Alloy.

- [ ] Copy the topology, fabric, client, gNMIc, Prometheus, and Grafana assets while retaining license headers.
- [ ] Remove Loki and Alloy nodes and the Loki Grafana datasource.
- [ ] Run `python3 -m unittest discover -s tests -v`; expected result after the static test is added: topology test passes.
- [ ] Commit with `git commit -m "feat: add phase 1 SR Linux telemetry lab"`.

### Task 2: Add parsing and readiness evaluation

**Files:**
- Create: `fabric_readiness/core.py`
- Create: `fabric_readiness/__init__.py`
- Create: `tests/test_core.py`
- Create: `readiness.toml`

**Interfaces:**
- Produces: `parse_iperf(payload) -> dict`, `parse_prometheus_value(payload) -> float`, and `evaluate(evidence, policy) -> tuple[str, list[dict]]`.

- [ ] Write tests with literal fixtures for successful and malformed `iperf3` output, Prometheus scalar values, and all three classifications.
- [ ] Run `python3 -m unittest tests.test_core -v`; expected result: import failure because `core.py` does not exist.
- [ ] Implement the minimum pure functions and TOML policy needed to pass.
- [ ] Run `python3 -m unittest tests.test_core -v`; expected result: all tests pass.
- [ ] Commit with `git commit -m "feat: add readiness evaluation"`.

### Task 3: Add report generation

**Files:**
- Create: `fabric_readiness/report.py`
- Create: `tests/test_report.py`

**Interfaces:**
- Consumes: experiment result dictionary containing `result`, `checks`, `measurements`, and `timeline`.
- Produces: `write_reports(result, output_dir) -> tuple[Path, Path]`.

- [ ] Write a test that generates reports in a temporary directory and checks parsed JSON plus important Markdown fields.
- [ ] Run `python3 -m unittest tests.test_report -v`; expected result: import failure because `report.py` does not exist.
- [ ] Implement deterministic JSON and Markdown report writers.
- [ ] Run `python3 -m unittest tests.test_report -v`; expected result: all tests pass.
- [ ] Commit with `git commit -m "feat: generate readiness reports"`.

### Task 4: Add experiment orchestration

**Files:**
- Create: `fabric_readiness/experiment.py`
- Create: `fabric_readiness/__main__.py`
- Create: `tests/test_experiment.py`

**Interfaces:**
- Consumes: policy from `readiness.toml`, Docker/gNMIc/Prometheus command boundaries.
- Produces: `Experiment.run() -> dict` and `python3 -m fabric_readiness run`.

- [ ] Write a fake command-boundary test proving the interface is restored after a fault-window error.
- [ ] Run `python3 -m unittest tests.test_experiment -v`; expected result: import failure because `experiment.py` does not exist.
- [ ] Implement preflight, baseline, fault injection, observations, cleanup, evaluation, reporting, and exit-code mapping.
- [ ] Run `python3 -m unittest tests.test_experiment -v`; expected result: all tests pass.
- [ ] Commit with `git commit -m "feat: automate the link failure experiment"`.

### Task 5: Add one-command use and documentation

**Files:**
- Create: `Makefile`
- Modify: `README.md`
- Create: `.devcontainer/devcontainer.json`
- Create: `.devcontainer/postCreateCommand.sh`

**Interfaces:**
- Produces: `make deploy`, `make experiment`, `make test`, and a Codespaces setup path.

- [ ] Add minimal make targets and a Codespaces setup script that installs Containerlab when absent.
- [ ] Document architecture, prerequisites, commands, readiness rules, report evidence, and upstream attribution.
- [ ] Run `make test`; expected result: all unit and static tests pass.
- [ ] Run `python3 -m compileall -q fabric_readiness`; expected result: exit 0.
- [ ] Commit with `git commit -m "docs: add one-command Codespaces workflow"`.
