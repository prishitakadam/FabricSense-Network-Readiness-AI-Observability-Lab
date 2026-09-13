# Network Fabric Observability & Readiness Lab

An automated resilience experiment for a virtual Nokia SR Linux leaf-spine
fabric. One command deploys the network and observability stack, measures a
healthy baseline, disables a leaf-spine link, measures degraded performance,
restores the link, and produces an evidence-based readiness result.

## Run the lab in GitHub Codespaces

1. Open this repository on GitHub and select **Code → Codespaces → Create
   codespace**. Choose a machine with at least 4 cores and 16 GB RAM.
2. Wait for the development container to finish starting.
3. Run:

```bash
make experiment
```

The initial image download can take 10–20 minutes. Later runs are faster.
The command waits up to three minutes for the fabric and telemetry to converge.

The final terminal output is:

```text
FINAL RESULT: PASS
Markdown report: artifacts/<experiment-id>/report.md
JSON evidence: artifacts/<experiment-id>/results.json
```

Exit codes are `0` for PASS, `1` for FAIL, and `2` for INCONCLUSIVE.

## Architecture

```text
client2 ─ leaf2 ─┬─ spine1 ─┬─ leaf1 ─ client1
                 └─ spine2 ─┘

SR Linux ──gNMI──> gNMIc ──scrape──> Prometheus ──> Grafana
     ^                                  |
     | gNMI Set                         | HTTP queries
     └──────── Python experiment runner ┘
```

The complete topology contains three leaves, two spines, and three Linux
clients. The automated experiment uses `client2 → client1` and disables
`leaf1/ethernet-1/49`, leaving the alternate path through `spine2` available.

## Open-source foundation and additions

This project extends Nokia's open-source
[SR Linux Telemetry Lab](https://github.com/srl-labs/srl-telemetry-lab). The
original lab provides the Containerlab-based SR Linux leaf-spine fabric, gNMIc
telemetry collection, Prometheus scraping, Grafana visualization, and topology
assets.

This repository keeps that observability foundation and adds a repeatable
readiness experiment around it:

- Python automation for fabric health validation, traffic benchmarking,
  controlled gNMI link failure, recovery measurement, and cleanup.
- Explicit PASS/FAIL/INCONCLUSIVE readiness rules backed by telemetry and
  benchmark evidence.
- Markdown and JSON report generation for human review and machine-readable
  evidence.
- Codespaces/devcontainer setup and tests so the lab can be reproduced and
  validated consistently.

The goal is to turn a telemetry demo into a resilience validation workflow:
deploy the fabric, observe it, inject a realistic link failure, measure the
impact, confirm recovery, and produce evidence that the network is ready.

## What the experiment checks

1. Required containers, endpoint reachability, Prometheus, and selected-link
   telemetry are healthy.
2. Eight parallel TCP streams establish baseline throughput with `iperf3`.
3. A gNMI Set request disables the selected leaf-spine interface.
4. Prometheus observes the failure and traffic succeeds over the remaining
   path.
5. The runner restores the link, measures recovery, and writes both reports.

The link restoration runs from a `finally` block, including when the benchmark
or telemetry query fails.

## Readiness policy

Thresholds are editable in [`readiness.toml`](readiness.toml):

```toml
[readiness]
minimum_baseline_mbps = 100.0
minimum_degraded_ratio = 0.70
minimum_recovered_ratio = 0.90
maximum_recovery_seconds = 30.0
maximum_telemetry_age_seconds = 15.0
maximum_error_delta = 0.0
```

- **PASS:** every health, degradation, recovery, telemetry, and restoration
  rule passes.
- **FAIL:** the experiment is trustworthy but the fabric violates a readiness
  threshold.
- **INCONCLUSIVE:** missing telemetry, unhealthy initial state, or a tooling
  failure prevents a trustworthy decision.

## Grafana and Prometheus

After deployment, use the Codespaces **Ports** tab to open:

- Grafana: port `3000` (anonymous access is enabled)
- Prometheus: port `9090`

The provisioned Grafana dashboard shows interface state and traffic rate across
the fabric.

## Development commands

```bash
make deploy      # deploy or recreate the lab
make experiment  # deploy and run the complete readiness experiment
make test        # run tests without deploying the lab
make destroy     # remove all lab containers and generated lab files
```

## Repository layout

```text
configs/             SR Linux, gNMIc, Prometheus, and Grafana configuration
fabric_readiness/    experiment runner, evaluation, and report generation
tests/               fast unit and static configuration tests
st.clab.yml          Containerlab topology
readiness.toml        scenario values and explicit readiness thresholds
artifacts/            generated experiment evidence (Git-ignored)
```

## Attribution

The topology and telemetry assets are derived from the open-source
[Nokia SR Linux Telemetry Lab](https://github.com/srl-labs/srl-telemetry-lab).
See [`NOTICE.md`](NOTICE.md) and
[`third_party/srl-telemetry-lab/LICENSE`](third_party/srl-telemetry-lab/LICENSE).
