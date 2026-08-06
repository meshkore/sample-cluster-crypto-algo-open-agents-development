# The contract between the three folders

This repository is split so that the community can work on one thing without
being able to break the thing that grades it.

```
backtester/            the instrument. Frozen. Decides nothing.
trading-system/        every decision. Variable. This is where you contribute.
orchestrator-manager/  the lab that runs them: loop, ledger, db, UI, cluster.
```

## Dependency direction, and why it is the whole point

```
orchestrator-manager  ──▶  trading-system  ──▶  backtester (data contract only)
        └───────────────────────────────────▶  backtester (engine)
```

`backtester/` imports **nothing** from the other two. That is checked, not
hoped for — see `orchestrator-manager/scripts/check_layering.py`, which fails the build if the
instrument ever learns about a strategy.

The consequence worth stating plainly: a contributed strategy **structurally
cannot** reach into position sizing, cost assumptions, drawdown accounting or
scoring. It can only produce signals and supply a policy object. Two
contributions are therefore comparable, because they were measured by the same
instrument on the same data.

## What lives where

### `trading-system/` — yours to change

Everything that makes a decision:

| module | what it decides |
|---|---|
| `strategies.py` | entry and exit signals, one family per hypothesis |
| `regime.py` | what market we are in |
| `regime_system.py` | which mechanism runs in which regime |
| `policy.py` | **money management** — sizing, stops, the drawdown mandate |

`policy.py` is in here deliberately. Sizing and stops are not plumbing: this
laboratory has repeatedly measured them mattering more than the entry rule, and
they are as much a hypothesis as anything else. A contributor may replace the
whole file — volatility targeting, Kelly, fixed fraction, a learned sizer —
without touching the instrument.

### `backtester/` — frozen

| module | what it does |
|---|---|
| `models.py` | `Bar`, the data format |
| `data.py` | the data puller |
| `backtest.py` | `CostModel`, single-asset execution |
| `engine.py` | portfolio execution, fills, equity curve, metrics |
| `walkforward.py` | the evaluation protocol |
| `validation.py`, `benchmark.py` | scoring and baselines |

### `orchestrator-manager/` — infrastructure

The research loop and its ledger (`loop/`), the experiment database, the
autonomous cycle, the champion selection, the dashboard, the public mirror, the
MeshKore cluster bridge.

## The two interfaces

### 1. Strategy

```python
class MyStrategy:
    def reset(self) -> None: ...
    def on_bar(self, bars: list[Bar]) -> float:
        """Confidence in [0, 1] for the LAST bar. Long-only: 0 means flat."""
```

Register it in `strategies.py` so `build_strategy(family, params, context)` can
construct it.

### 2. Policy

The engine never imports your policy. It reads the members listed in
`backtester/quantlab_backtester/engine.py::SizingPolicy` — a structural
`Protocol`, so you inherit from nothing. Supply any object carrying them.

## Rules a contribution must satisfy

1. **No lookahead.** `on_bar(bars)` may read `bars` and nothing else. A label
   or indicator used to trade bar *N* must be computable from bars `1..N-1`.
   The conformance suite checks this by prefix equality across many cut points.
2. **`reset()` must actually reset.** The engine reuses instances across
   assets. State surviving a reset silently shares information between symbols.
3. **Signal range.** `on_bar` returns a float in `[0, 1]`. Long-only is a hard
   project constraint, not a default.
4. **Sabotage your own tests.** Break the code the test is supposed to catch and
   confirm the test fails. This project has twice shipped tests that passed
   against deliberately broken code, and both times they looked reasonable.
5. **Never touch `backtester/` in a strategy PR.** If you believe the instrument
   is wrong, that is a separate PR with its own argument — see below.

## Changing the instrument

"Immutable because it does not affect results" would be a comfortable belief and
it is false. In this laboratory the instrument has produced nearly every wrong
answer we have found:

- the de-leverage ramp's path dependence manufactured a **+4,705%** winner that
  did not exist (H-009); with the ramp off, every value of the parameter being
  "optimised" returned an identical number;
- peak-basis drawdown accounting bricked a strategy for four and a half years
  while the monitor reported it as live and up +1,480%;
- exposure went unrecorded for eight months, which made +3.46% and +350%
  equally unreadable;
- two evaluators silently dropped a policy field, moving average exposure from
  8.1% to 18.7% and turning a legal run into an aborted one.

So the instrument is frozen for **fairness**, not because it is harmless. A
change to it invalidates every recorded result, and the rule is:

1. open it as its own PR, never bundled with a strategy;
2. state which recorded results it invalidates;
3. bump `backtester/VERSION`;
4. re-run the ledger's recorded hypotheses under the new version before any new
   number is quoted against an old one.

## Running things

```bash
export PYTHONPATH=backtester:trading-system:orchestrator-manager

python3 -m unittest discover -s backtester/tests           -t backtester/tests
python3 -m unittest discover -s trading-system/tests       -t trading-system/tests
python3 -m unittest discover -s orchestrator-manager/tests -t orchestrator-manager/tests

python3 orchestrator-manager/scripts/check_layering.py     # the dependency rule above
```
