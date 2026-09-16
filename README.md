# FabricSense: Network Readiness & AI Observability Lab

A virtual Nokia SR Linux Clos fabric lab for network resilience validation and
AI-assisted observability. The project deploys a Containerlab leaf-spine fabric,
streams switch telemetry into Prometheus and Grafana, runs controlled traffic
and link-failure experiments, generates evidence-based readiness reports, and
exposes read-only MCP tools so an AI assistant can investigate live fabric
telemetry.

## Run the lab in GitHub Codespaces

1. Open this repository on GitHub and select **Code → Codespaces → Create
   codespace**. Choose a machine with at least 4 cores and 16 GB RAM.
2. Wait for the development container to finish starting.
3. Deploy the lab:

```bash
make deploy
```

4. Run the readiness experiment:

```bash
make experiment
```

For noisy virtual-lab runs, keep the default policy in `readiness.toml` and
override the interface error threshold only for that run:

```bash
make experiment ARGS="--maximum-error-delta 2000"
```

Use `make all` when you want to deploy and run the experiment in one command.
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
Traffic path:
client2 ─ leaf2 ─┬─ spine1 ─┬─ leaf1 ─ client1
                 └─ spine2 ─┘

Telemetry and investigation path:
SR Linux switches ──gNMI──> gNMIc ──scrape──> Prometheus ──> Grafana
        ^                                      │
        │ gNMI Set                             │ PromQL / HTTP
        └──── Python readiness runner          └──── MCP server ──> AI assistant

Evidence and analysis outputs:
Python readiness runner ──> Markdown readiness report and JSON evidence bundle
MCP-enabled assistant    ──> Natural-language investigation of live Prometheus telemetry
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
[experiment]
iperf_mss = 1200

[readiness]
minimum_baseline_mbps = 20.0
minimum_degraded_ratio = 0.70
minimum_recovered_ratio = 0.90
maximum_recovery_seconds = 30.0
maximum_telemetry_age_seconds = 15.0
maximum_error_delta = 0.0
```

`iperf_mss` keeps TCP benchmarking stable in virtual/container labs where
default large TCP segments can produce misleading zero-throughput results.
`maximum_error_delta` can also be overridden per run with
`--maximum-error-delta` when a virtual lab reports expected counter noise during
an intentional link flap.

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

## AI-assisted fabric investigation with MCP

This repository includes a read-only MCP server that exposes Prometheus-backed
fabric investigation tools to an AI agent such as Codex or Claude. The agent
can answer natural-language questions by querying live telemetry, without
requiring a manual report path, screenshot, or PromQL query.

### MCP investigation example

With the MCP server connected, an engineer can investigate a failure in plain
English while an AI agent, such as Codex or Claude, turns each question into
read-only Prometheus queries. For example:

**Question: Is telemetry healthy right now?**

**Codex / AI agent answer:** Yes. Prometheus is successfully scraping gNMIc:
`up{job="gnmic"} = 1` for `gnmic:9273`. No telemetry targets are down.

**Question: What happened in the last 10 minutes?**

**Codex / AI agent answer:** A recent fault occurred. Telemetry stayed healthy,
but one fabric link flapped:

- `spine1:e1-1` changed state 2 times.
- `leaf1:e1-49` changed state 2 times.

The most likely failed link was `spine1:e1-1 <-> leaf1:e1-49`.

**Question: What evidence shows the fault?**

**Codex / AI agent answer:**

- Both ends changed together: `up -> down` at `21:54:38`, then `down -> up`
  at `21:54:53`.
- The outage lasted about 15 seconds.
- Error counters increased during the window, especially on `leaf1:e1-50`,
  `leaf1:e1-49`, and `leaf1:e1-1`.

**Question: Did traffic continue and route around the failure?**

**Codex / AI agent answer:** Yes. Client-facing traffic on `leaf1:e1-1`
continued and peaked around `40.6 Mbps`. Traffic on the failed path,
`spine1:e1-1` and `leaf1:e1-49`, dropped near zero while alternate-path
traffic rose on `spine2:e1-1` and `leaf1:e1-50`.

**Question: Was recovery successful?**

**Codex / AI agent answer:** Yes. Both failed-link endpoints returned to
`oper_state=1`, telemetry stayed healthy, and traffic continued during and
after the event.

**Question: Which interfaces should be investigated first?**

**Codex / AI agent answer:**

1. `leaf1:e1-50` - largest error increase and likely failover path.
2. `leaf1:e1-49` - failed link endpoint.
3. `spine1:e1-1` - other failed link endpoint.
4. `leaf1:e1-1` - client-facing interface with significant errors.
5. `leaf2:e1-1`, `leaf2:e1-50`, `leaf2:e1-49` - secondary error increases.

Start the MCP server from the repository root:

```bash
python3 -m pip install -r requirements.txt
python3 -m mcp_servers.fabric_prometheus.server
```

By default it queries Prometheus at `http://localhost:9090`. Override that when
Prometheus is forwarded elsewhere:

```bash
PROMETHEUS_URL="https://<prometheus-forwarded-url>" \
python3 -m mcp_servers.fabric_prometheus.server
```

For Codespaces URLs that change often, keep the current URL in a local ignored
file and point the MCP server at that file:

```bash
mkdir -p .local
printf '%s\n' 'https://<prometheus-forwarded-url>' > .local/prometheus-url

PROMETHEUS_URL_FILE="$PWD/.local/prometheus-url" \
python3 -m mcp_servers.fabric_prometheus.server
```

If your local Python install does not trust the Codespaces forwarded
certificate chain, use the development-only TLS bypass:

```bash
PROMETHEUS_URL="https://<prometheus-forwarded-url>" \
PROMETHEUS_INSECURE_SKIP_VERIFY=1 \
python3 -m mcp_servers.fabric_prometheus.server
```

To install this server in Codex, add an MCP entry to your local Codex config
using the absolute path to this repository checkout:

```toml
[mcp_servers.srl_fabric_prometheus]
command = "python3"
args = [
  "-m",
  "mcp_servers.fabric_prometheus.server"
]
startup_timeout_sec = 10

[mcp_servers.srl_fabric_prometheus.env]
PYTHONPATH = "/absolute/path/to/Network-Fabric-Observability-Resilience-Testing"
PROMETHEUS_URL_FILE = "/absolute/path/to/Network-Fabric-Observability-Resilience-Testing/.local/prometheus-url"
PROMETHEUS_INSECURE_SKIP_VERIFY = "1"
```

Restart Codex after editing the config so the MCP server is loaded.
When Codespaces gives you a new forwarded URL, update only `.local/prometheus-url`
and restart Codex.

The MCP server is intentionally read-only. It can query Prometheus, but it
cannot run shell commands, disable links, repair links, or change SR Linux
configuration.

Supported investigation tools include:

- `fabric_down_links`
- `fabric_link_changes`
- `fabric_interface_errors`
- `fabric_top_traffic`
- `fabric_telemetry_health`
- `prometheus_instant_query`
- `prometheus_range_query`

Good questions for the assistant:

- Which interfaces changed state in the last 30 minutes?
- Are any fabric links down right now?
- Which interfaces reported errors recently?
- Which links have the highest outbound traffic?
- Is Prometheus successfully scraping gNMIc?
- Did traffic appear on the alternate spine path?

The MCP server only has Prometheus/Grafana telemetry context. It should not
claim a final readiness `PASS` or `FAIL` unless that result is exported as a
metric; use the Markdown/JSON readiness report for final experiment verdicts.

## Development commands

```bash
make deploy      # deploy or recreate the lab
make experiment  # run the readiness experiment against an existing lab
make experiment ARGS="--maximum-error-delta 2000"
make all         # deploy the lab, then run the readiness experiment
make setup       # install Python dependencies for MCP support
make test        # run tests without deploying the lab
make destroy     # remove all lab containers and generated lab files
```

## Repository layout

```text
configs/             SR Linux, gNMIc, Prometheus, and Grafana configuration
fabric_readiness/    experiment runner, evaluation, and report generation
mcp_servers/         read-only MCP server for Prometheus-backed AI investigation
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
