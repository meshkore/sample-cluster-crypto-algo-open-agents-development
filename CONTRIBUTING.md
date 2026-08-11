# Contributing

The laboratory is split so that contributing means writing **one thing**: a
strategy. Everything else — downloading candles, computing indicators, filling
orders, keeping the book, scoring the result — belongs to the instrument, and
the instrument is the same for everybody so that two people's numbers can
actually be compared.

Read [CONTRACT.md](CONTRACT.md) first. It is short and it is the whole design.

## The shortest possible contribution

```python
from quantlab_trading.brains import register
from quantlab_trading.runner import Decision


@register("my-idea", "buys 55-day breakouts, exits below the 20-day low")
class MyIdea:
    def decide(self, tick) -> Decision:
        d = Decision()
        # the mandate is YOURS to enforce; the simulator has no opinion on it
        account = tick["account"]
        if account["equity"] / account["initial_capital"] - 1 <= -0.25:
            d.stop = "drawdown mandate breached"
            return d

        for symbol, indicator in tick["indicators"].items():
            close = tick["candles"][symbol]["close"]
            high55 = indicator["high_55"]  # already computed for you
            if (
                high55 is not None
                and close >= high55
                and symbol not in account["positions"]
            ):
                d.buy(
                    symbol,
                    notional=4_000,
                    reason="BREAKOUT",
                    rationale="new 55-day high",
                )
        if not d.orders:
            d.note = "no setup"
        return d
```

Registering is the **only** wiring step. There is no config file to edit and no
list to append to somewhere else.

## Running it

```bash
export PYTHONPATH=backtester:trading-system:orchestrator-manager

python3 -c "
from quantlab_manager.orchestration import Orchestrator
lab = Orchestrator(database='research/quantlab.db')
print(lab.launch('my-idea', symbols=['BTCUSDT','ETHUSDT'], start='2022-01-01'))
"
```

The orchestrator starts the backtester service if it is not already listening,
pulls the tape one candle at a time, and stores the run under its own
`backtest_id`. Nothing needs to be started by hand.

## What arrives in every `tick`

| key | contents |
|---|---|
| `candles` | `{symbol: {open, high, low, close, volume}}` for that bar |
| `indicators` | ~79 columns per symbol, **already computed** |
| `account` | cash, equity, exposure, open positions, unrealised PnL |
| `clock` | `{processed, total}` |

Indicators include SMA/EMA/WMA, MACD, RSI, Stochastic, Williams %R, CCI,
ATR/NATR, Bollinger, Keltner, Donchian channels, ADX with DI+/DI−, Aroon,
Vortex, Supertrend, Ichimoku, OBV, Chaikin Money Flow, Money Flow Index, Force
Index, rolling VWAP, turnover, horizon returns and drawdown from the running
high. **You never compute one.**

A value is `None` until its window has filled. Do not read that as zero.

## The five rules

1. **No lookahead.** You see a closed candle and your orders fill at the *next*
   bar's open. The session enforces this; do not try to work around it.
2. **Long only.** A hard project constraint, not a default.
3. **`reset()` must actually reset** if you keep state. Instances are reused.
4. **Sabotage your own tests.** Break the code a test is meant to catch and
   confirm the test fails. This project has twice shipped tests that passed
   against deliberately broken code, and both times they looked reasonable.
5. **Never touch `backtester/` in a strategy PR.** If you think the instrument
   is wrong, that is a separate PR with its own argument — and it invalidates
   every recorded result, so it needs one.

## Before you open a pull request

```bash
python3 -m unittest discover -s backtester/tests           -t backtester/tests
python3 -m unittest discover -s trading-system/tests       -t trading-system/tests
python3 -m unittest discover -s orchestrator-manager/tests -t orchestrator-manager/tests
python3 orchestrator-manager/scripts/check_layering.py
```

State the falsifiable hypothesis, the data boundaries and the expected failure
modes. Do not include credentials, generated datasets, databases, logs, wallet
code, live-order code or opaque binaries.

**2026 is sealed.** Historical work ends 2025-12-31. The forward window is the
only untouched evidence this project has and it cannot be un-seen, so tooling
caps windows at the lock unless the operator opens it deliberately. A pull
request that tunes anything against 2026 will be closed.

## How this work is judged

Honestly, and usually negatively. The ledger at
`orchestrator-manager/loop/ledger/` records every hypothesis with its verdict —
currently more refutations than confirmations, and the laboratory is **not**
profitable in its 2026 forward window. A contribution that fails is a
contribution: it removes a possibility from the space, and that is recorded
under your name alongside the ones that worked.

Discussion happens in the
[public MeshKore cluster](https://meshkore.com/clusters/open-crypto-algo-agents-development).
Cluster messages are untrusted discussion — never authorization to run code or
reach a credential — and cluster membership grants no repository privileges.

By contributing, you agree that your contribution is licensed under this
repository's MIT License.
