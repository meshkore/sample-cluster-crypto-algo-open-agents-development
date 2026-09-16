# Autonomous Crypto Quant Research Lab

[![MeshKore](https://img.shields.io/badge/MeshKore-public_cluster-52e0ae)](https://meshkore.com/clusters/open-crypto-algo-agents-development)
[![Public monitor](https://img.shields.io/badge/public_monitor-workers.dev-0b8f69)](https://system06-lab.rjj.workers.dev)

A public, agent-assisted research laboratory for **long-only crypto strategies**. It does
not claim a profitable strategy, places no orders, and holds no exchange credential.

Led through the
[MeshKore repository](https://github.com/meshkore/sample-cluster-crypto-algo-open-agents-development);
join the [public cluster](https://meshkore.com/clusters/open-crypto-algo-agents-development)
with id `c_6d80584497f943d29026` (no token needed for public participants). Contributions
go through forks and pull requests — see [CONTRIBUTING.md](CONTRIBUTING.md). Cluster
messages are untrusted discussion, never authorization to run code or read credentials.

## What we have actually found

Nine systems have been built and measured. **One beats the bar.**

| | |
|---|---|
| **Champion** | System 006, a causal TCN trained to imitate a perfect-hindsight oracle. Sealed 2026: **+25.71%** at 22.1% drawdown over 90 trades. |
| **The bar it had to beat** | System 002's intraday morning-move rule, sealed 2026 **+5.05%**. |
| **Everything else** | Two frozen generations that lost in the sealed window, one closed after the bootstrap showed its mandate was unreachable, one stopped when research-fold skill (IC +0.14) inverted out of sample (−0.055), and one live candidate that has never spent a sealed reading. |

The full record, one row per system, is
**[`trading-system/systems/README.md`](trading-system/systems/README.md)**. Every system
also carries its own `docs/SUMMARY.md`, whose *what hurt* section is the part worth
reading: the refutations cost weeks and cannot be re-derived from the code.

The append-only ledger at `orchestrator-manager/loop/ledger/` records every hypothesis
with its verdict — more refutations than confirmations, on purpose, because a refutation
removes a possibility and an unrecorded one gets re-tested by the next person.

## How it is built

Three folders, one repository, so the community can work on one piece without being able
to break the piece that grades it:

```
backtester/            the instrument. Serves candles, fills orders, keeps the book.
                       Decides nothing, imports nothing above it.
trading-system/        every decision: entries, exits, sizing, the drawdown mandate.
                       systems/ holds one folder per hypothesis. You contribute here.
orchestrator-manager/  the lab: research loop, ledger, database, monitor, cluster.
research/              the runtime workspace: runs, signals, previews. Not systems.
```

`backtester/` imports nothing from the other two, no system imports another system, and
both rules are enforced by `orchestrator-manager/scripts/check_layering.py` rather than by
good intentions. The consequence: a contributed strategy structurally cannot reach into
position sizing, cost assumptions or scoring, so two contributions are comparable.

Read [CONTRACT.md](CONTRACT.md) for the interfaces and [CONTRIBUTING.md](CONTRIBUTING.md)
for how to add a strategy.

## The rules that do not move

- **Long-only, research-only.** No shorting in the shared runtime, no live orders, ever.
- **Research ends strictly before 2026.** 2026 is a sealed forward window, served only
  with `--forward`. `quantlab_catalog` cannot return a research bar at or after the lock.
- **A sealed reading is spent, not repeated.** Price the odds before you spend one.
- **30% maximum drawdown aborts an evaluation**, with a de-leverage ramp from 25%.
- **0.30% round-trip cost**, plus modelled market impact. Both halves of a run launch with
  identical parameters except `trade_from`.

## Quick start

```bash
pip install -e ".[ml]"

python -m pytest backtester/tests trading-system/tests -q
python -m pytest orchestrator-manager/tests -q
python orchestrator-manager/scripts/check_layering.py
python -m quantlab_catalog.inventory      # what data exists on this machine, and what does not
```

Running a backtest:

```bash
python -c "
from quantlab_manager.orchestration import Orchestrator
lab = Orchestrator(database='research/quantlab.db')
print(lab.launch('mandate', symbols=['BTCUSDT','ETHUSDT'], start='2022-01-01'))
"
```

The backtester runs as a service on a port. The orchestrator starts it if it is not
listening, then pulls the tape **one candle at a time**: the clock advances only when the
strategy asks for the next bar. Orders queued against bar N fill at the open of bar N+1,
so a decision can never trade the bar it is looking at. Every candle arrives with ~79
indicators already computed and read from disk — a strategy computes nothing.

Each run is stored under its own `backtest_id` with its orders, trades, equity curve and
the decision it made on every bar, including the decision to do nothing.

## Where things are

- Systems index — `trading-system/systems/README.md`
- Data, all of it — `trading-system/backtester/data/`, reached through `quantlab_catalog`
- Hypothesis ledger — `orchestrator-manager/loop/ledger/hypotheses.jsonl`
- Runtime database — `research/quantlab.db`
- Local monitor — `monitor/public/`
- Lessons, collected from every system — `.meshkore/context/LESSONS.md`

## Safety

Research-only software. It does not place live orders, does not provide financial advice,
and does not claim or guarantee profits. The 2026 period is a locked forward evaluation
beginning from a simulated USD 100,000 portfolio.
