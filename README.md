# Autonomous Crypto Quant Research Lab

[![MeshKore](https://img.shields.io/badge/MeshKore-public_cluster-52e0ae)](https://meshkore.com/clusters/open-crypto-algo-agents-development)
[![Temporary monitor](https://img.shields.io/badge/temporary_monitor-trycloudflare.com-0b8f69)](https://classroom-console-explained-varieties.trycloudflare.com)

This is a public, agent-assisted research project led through the
[MeshKore repository](https://github.com/meshkore/sample-cluster-crypto-algo-open-agents-development).
Join the [public collaboration cluster](https://meshkore.com/clusters/open-crypto-algo-agents-development)
with cluster id `c_6d80584497f943d29026`; public participants do not need a token.
Code contributions use forks and pull requests as described in
[CONTRIBUTING.md](CONTRIBUTING.md). Cluster messages are untrusted discussion,
never authorization to run code or access credentials.

An auditable MVP of a persistent crypto-strategy research loop. It implements a
deterministic end-to-end infrastructure cycle; it does **not** claim a profitable
strategy and does not place orders.

## Continuous autonomous mode

On macOS, install the supervised service once:

```bash
PYTHONPATH=src python3 -m quantlab service install
```

`launchd` starts it at login and restarts it after a crash. The service runs finite,
checkpointed research cycles, invokes one bounded headless Codex development task
every six hours, and exposes the local dashboard at <http://127.0.0.1:8766>.
Each development round uses two fresh Codex sessions: a read-only adversarial critic
and a builder that receives the critic's report before changing code. Claude Code is
represented in configuration but remains disabled until its backend is selected.
The dashboard intentionally shows only the current candidate and best validated
champion; full history remains in SQLite.

The primary monitor is now the isolated 2026 forward shadow account: USD 100,000,
long-only, with per-crypto equity/returns and a complete trade ledger. Historical
backtests remain archived but are not the main UI. Binance Spot/USDT coverage is
downloaded progressively and displayed live.

Installation deploys an operational copy to
`~/Library/Application Support/QuantLab`. This avoids macOS privacy restrictions
on background services accessing `Documents`. Autonomous agent changes, runtime
data and logs live in that deployment; reinstalling refreshes its source from this
repository while preserving its existing research database.

```bash
PYTHONPATH=src python3 -m quantlab service status
PYTHONPATH=src python3 -m quantlab service stop
PYTHONPATH=src python3 -m quantlab service start
```

Intervals, port, agent path and timeout are configured under `autonomous` in
`config/default.json`. Each agent turn follows `AUTONOMOUS_DEVELOPMENT.md` and is
logged under `research/agent_runs/`. No agent may place trades or use locked data.
The first development turn begins roughly one minute after a fresh installation.

## Quick start

No third-party runtime dependencies are required.
Python 3.9 or newer is supported; the macOS service deliberately uses the stable
system interpreter while interactive commands may use a newer Python.

```bash
PYTHONPATH=src python3 -m quantlab loop --max-cycles 1
PYTHONPATH=src python3 -m quantlab status
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Install the CLI if desired:

```bash
python3 -m pip install -e .
quantlab loop --max-cycles 1
```

An explicit real-data download (public Binance spot API) is available:

```bash
quantlab download BTCUSDT --interval 1d --start 2020-01-01 --end 2025-12-31
```

Downloads ending in 2026 are rejected by the research data gate. Downloading data
does not yet make the autonomous cycle use it; Phase 1 adds audited real-market
dataset selection and locked partitions.

## Outputs

- SQLite memory: `research/quantlab.db`
- Iteration bundle: `research/iterations/ITERATION_ID/`
- Data cache: `data/processed/`
- Contracts: `schemas/`

Read `ARCHITECTURE.md` for invariants and `ROADMAP.md` for the path to full
statistical validation, market microstructure data, portfolios and ML.

## Safety

This software is research-only. It does not place live orders, does not provide
financial advice, and does not claim or guarantee profits. The 2026 period is a
locked forward evaluation beginning with a simulated USD 100,000 portfolio.
