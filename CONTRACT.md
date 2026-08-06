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

## How work actually happens: an agent launches it

Neither half works alone. A strategy with no tape decides nothing; a tape with
no strategy is a CSV reader. So the **orchestrator owns both** — it makes sure
the backtester is listening, hands the brain the wire, and writes the result
down. Nothing waits for a human to type.

The whole autonomous path is three steps:

```python
# 1. write a brain and register it — this is the only wiring step there is
from quantlab_trading.brains import register
from quantlab_trading.runner import Decision

@register("breakout-55", "buys 55-day breakouts, exits below the 20-day low")
class Breakout55:
    def decide(self, tick) -> Decision: ...

# 2. launch it. The backtester is started if it is not up, reused if it is.
from quantlab_manager.orchestration import Orchestrator
lab = Orchestrator(database="research/quantlab.db")
result = lab.launch("breakout-55", symbols=["BTCUSDT"], start="2022-01-01")

# 3. the run is already persisted under its id
result["backtest_id"], result["return_pct"], result["trades"]
```

`lab.strategies()` lists everything registered, so an agent can see its own work
and everyone else's.

Registering is deliberately the *only* step between writing a brain and having
the laboratory able to launch, backtest, persist and display it. There is no
config file to edit and no list to append to elsewhere — a second place to
update is a second place to forget, and a strategy that exists but cannot be
found is worse than one that does not, because nobody knows it is missing.

Two properties of `launch` worth knowing:

- **The orchestrator drives the pull loop over HTTP**, not in-process. It asks
  for a candle, hands it to the brain, sends back the decision, asks for the
  next. The wire is exercised on every real run, so a protocol bug cannot hide.
- **The record is read back from the backtester before it is stored.** The
  orchestrator does not hold the book, so it fetches orders, equity and
  decisions from the service and persists those. Storing what it *believed* it
  sent would make the record a transcript of intentions rather than of fills.

The command line (`quantlab_manager.backtest_cli`) is a **human window** for
`list` and `show`, not how work happens. Its `run` drives in-process and so does
not exercise the wire; prefer the Orchestrator for anything that matters.

## The backtester is a service you can start

```bash
export PYTHONPATH=backtester:trading-system:orchestrator-manager
python3 -m quantlab_backtester.server --port 8770
```

It binds a port, holds no key, reaches no venue, and can place no real order.
Everything is HTTP/JSON — MeshKore's mandatory baseline — so any language or
agent can drive a run without a client library.

| call | what it does |
|---|---|
| `POST /sessions` | create a run from a config, returns `backtest_id` |
| `GET /sessions/{id}/next` | **advance one bar**: candle + indicators + account |
| `POST /sessions/{id}/orders` | queue orders against the tick just served |
| `POST /sessions/{id}/stop` | end the run — the trading system's call |
| `GET /sessions/{id}/events` | Server-Sent Events for the visualiser |

Two properties are the design, not details:

**The clock only moves on `GET /next`.** There is no timer anywhere in the
process. A brain that needs a second to think costs itself a second; a fast one
runs flat out. This is why the tape is pulled rather than pushed.

**Orders queued against tick N fill at the OPEN of tick N+1.** A decision is
made after seeing a candle close, so it cannot trade inside the bar it is
looking at. Every lookahead this laboratory has caught came from blurring that
line, so the session enforces it structurally rather than by convention.

### Who owns what

| | backtester | trading system |
|---|---|---|
| downloading data | ✅ | |
| precomputing indicators | ✅ | |
| the clock | ✅ | |
| filling orders, costs, slippage | ✅ | |
| cash, holdings, the order log | ✅ | |
| **what to buy, and how much** | | ✅ |
| **when to sell** | | ✅ |
| **position sizing, the drawdown mandate** | | ✅ |
| **when to stop the run** | | ✅ |

The backtester is brainless in a precise sense: it has no *opinion*. It never
chooses anything, it only serves candles and executes what it is told. Filling
an order is exchange mechanics, not a decision, which is why it stays on the
instrument side — if every contributor computed their own fills, two strategies
would be graded by two different models and their numbers would not be
comparable.

Conversely the mandate is enforced by the **brain**, not the simulator. The
backtester has no view on whether a 25% loss should end a run, and contributors
will legitimately disagree. So `stop` is a request the trading system makes.

### The whole contribution surface

```python
from quantlab_trading.runner import Decision, run_backtest

class MyBrain:
    def decide(self, tick) -> Decision:
        # tick = {candles, indicators, account, clock, sequence, timestamp}
        d = Decision()
        if tick["account"]["equity"] / tick["account"]["initial_capital"] - 1 <= -0.25:
            d.stop = "drawdown mandate breached"
            return d
        for symbol, ind in tick["indicators"].items():
            if ind["sma_50"] and tick["candles"][symbol]["close"] > ind["sma_50"]:
                d.buy(symbol, notional=4_000, reason="TREND", rationale="above 50d")
        return d

run_backtest(MyBrain(), {"label": "mine", "symbols": ["BTCUSDT"]})
```

`MandateBrain` in `trading-system/quantlab_trading/runner.py` is the worked
reference: every number in it is a decision and every decision is in that one
file. Read it before writing your own.

### Indicators arrive precomputed — a brain derives nothing

Every tick carries ~79 indicator columns already calculated: SMA/EMA/WMA, MACD,
RSI, Stochastic, Williams %R, CCI, ATR/NATR, standard deviation, Bollinger,
Keltner, Donchian channels, ADX with DI+/DI−, Aroon, Vortex, Supertrend,
Ichimoku lines, OBV, Accumulation/Distribution, Chaikin Money Flow, Money Flow
Index, Force Index, rolling VWAP, turnover, horizon returns and drawdown from
the running high.

They are **backfilled once** and read from disk:

```bash
python3 -m quantlab_manager.backfill        # one pass over the universe
```

One gzipped CSV per (symbol, spec). The spec is hashed into the filename and the
header carries a digest of the OHLCV stream the panel was built from, so a cache
computed on different candles or different parameters is discarded rather than
served. That failure mode is the reason the digest exists: a stale cache is
indistinguishable from a correct one until a result has already been published.

**No TA library.** These formulas are written out because a pip package
computing the numbers that decide trades is a dependency this project's
contribution model would have to audit on every PR. Each formula is tested, and
RSI in particular is anchored to hand-computed values — a monotone series pins
RSI at 100 under any smoothing, so nothing else distinguishes Wilder from a
plain average.

**Warm-up is skipped, not merely flagged.** `IndicatorSpec.warmup_bars()` is the
longest window in the catalogue (252 bars by default), and a session trims those
bars from the front of its timeline. A 200-day average is wrong for its first
200 bars and a brain reading it cannot tell, so the session does not serve them.
Pass `skip_warmup: false` in the session config if you want them anyway.

Indicator values are `None` until their window fills. That is deliberate rather
than zero-filled — a rule comparing against zero would read a warm-up bar as a
real signal.

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
