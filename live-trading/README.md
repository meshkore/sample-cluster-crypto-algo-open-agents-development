# live-trading — the execution layer

Everything else in this repository exists to *find* a system. This folder exists to
**run** one, on live prices, from 2026-09-17 11:00 Europe/Madrid onwards.

Operator, 2026-09-17: *"2026 is our forward testing and it reaches today. From today on
we need a system that listens to prices in real time and fires the orders. Ideally a
simulation of where the order goes in, that computes the real slippage using Binance's
real-time spreads... When you have a better algorithm you simply change the engine, but
we keep trading. What we want is to trade with the best system we have at each moment,
so it has to be replaceable — the money-management functions, the model that makes the
decisions — and it has to manage the current portfolio as it stands, and decide from that
portfolio with the money it has available."*

## The three-folder contract, extended

| folder | what it is | who may import it |
|---|---|---|
| `backtester/` | the frozen instrument: fills, costs, the account | everybody |
| `trading-system/` | the systems: one brain per folder, numbered by date | the lab, the live layer |
| `orchestrator-manager/` | the lab: runs, ledgers, comparisons | nobody |
| **`live-trading/`** | **the execution layer: real prices, a real book, real orders** | **nobody** |

`live-trading/` is a LEAF. It imports the backtester's models and one system's brain, and
nothing imports it. That is what keeps it from disturbing research: no experiment, no
score, no ledger anywhere else in this repository changes because this folder exists or
because it is running.

## The one non-negotiable: the brain is not reimplemented

`quantlab_core.runner.Brain` is already the whole contract:

```python
decision = brain.decide(tick)     # tick: {timestamp, candles, account}
```

The backtester builds that tick from history; this layer builds the identical tick from
live candles and the live book. **The same `OracleNetBrain` object, the same
`Channels` table, the same thresholds and the same risk levers** decide in production as
in the backtest. A live layer that re-derived the strategy would be a second, untested
system wearing the first one's name — and every number this laboratory has measured would
stop describing the thing that is actually trading.

What differs between backtest and live is only what must:

| | backtest | live |
|---|---|---|
| bars | replayed from disk | polled from Binance as they close |
| channels | `signals.npz`, precomputed for all history | computed each bar for the new timestamp, appended to the same table |
| fill | next-bar open + modelled cost | the real book's bid/ask at decision time + the same impact model |
| clock | pulled as fast as the CPU allows | 15 minutes, waited out |

## Layout

```
live-trading/
  quantlab_live/
    config.py      paths, universe, cutover, credentials (loaded from OUTSIDE the repo)
    feed.py        Binance market data: closed candles + the live book
    book.py        the portfolio: cash, holdings, realised/unrealised, the order ledger
    brokers/
      base.py      the Broker protocol every venue implements
      paper.py     simulated fills at the REAL spread, with the lab's impact model
    engine.py      the swappable brain: an engine package -> a live Channels table
    trader.py      the loop: wait for a bar, decide, execute, publish
    state.py       live_state.json for the monitor
  engines/
    current.json   which engine package is live right now
    <version>/     manifest.json + net weights + standardizer + band/risk
  state/           the live book, the order ledger, the published state (gitignored)
```

## Swapping the engine without stopping the trading

An **engine package** is a directory under `engines/` holding everything needed to make
decisions: the net's weights, its standardizer, the feature config, the entry/exit band,
the risk levers, and a manifest recording where it came from and what it scored.
`engines/current.json` names the live one.

The trader re-reads `current.json` **between bars**, never inside a decision. When it
changes it rebuilds the brain, writes an `ENGINE_SWAP` row into the order ledger, and
carries on — **the portfolio is untouched**. Positions opened by version N are managed by
version N+1 exactly as they stand, because the brain only ever sees the account as it is.

That is the whole upgrade story: research promotes a package, the trader picks it up at
the next candle, the book never resets.

## Safety

* **Credentials live outside the repository**, in `~/.quantlab_live_env`, and are read
  only by `config.credentials()`. Nothing in this folder prints, logs or publishes a key.
* **Paper by default.** The paper broker is the only one wired. A venue broker that can
  move real money requires both a key file and an explicit `--venue` flag, and refuses to
  start without a written per-run confirmation.
* **What it writes.** Its own book, ledger and published state under `state/`, and
  nothing else that anyone reads for a result. It does extend two SHARED caches, because
  refusing to would mean a second copy of the market: the candle cache (new 15m candles
  as they close) and the content-addressed indicator cache. Both are additive - a new
  hash beside the old files - and neither is an input to any recorded score.
* **The engine refuses to trade degraded.** If an overlay a lever depends on is missing or
  stale, `Channels` would silently make that module abstain — a different strategy under
  the same name. The trader checks the manifest's declared levers against what it can
  actually feed, and stops rather than trading something it cannot describe.
