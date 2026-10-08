# System 10 — improvement catalogue

Things to verify, test, and adopt or drop. Each item gets a status and, once tested, the
measured result. The 8-hourly review (`review.py`) and the search work through it; the
operator does not have to ask.

Status: `queued` · `running` · `adopted` · `dropped` (with the reason) · `idea`

The operator, 2026-10-08: *"a 50% drawdown is too risky. We need a model that perhaps
earns less but does not expose the account... Maybe the model is one thing and the trading
system can be improved through money management... detect conditions where we fail
consistently and do not trade them... Pareto: if 80% of the winning trades happen in
certain conditions, trade only those... and keep evolving."*

## A. Money management (the book, not the model)

| # | Item | Status | Result |
|---|---|---|---|
| A1 | Drawdown cap: no year above 25% max DD is eligible | adopted 2026-10-08 | release 20 (DD 45–53%) no longer qualifies; no earlier trial met it |
| A2 | Account stop: close all and pause 3 days when the book is X below its peak (8/12/16/20%) | running | search lever `book_stop` |
| A3 | Tighter per-trade stop (5/8/12% vs 16.3%) | running | search lever `stop` |
| A4 | More, smaller positions (5 or 8 slots instead of 3) | running | search lever `slots` |
| A5 | Volatility targeting: stake ∝ target vol / recent vol | queued | |
| A6 | Correlation limit: at most N positions in coins moving together | idea | |
| A7 | Equity-curve filter: halve stakes while the account is below its own 30-day average | idea | |

## B. Pareto filters: trade only where we win

| # | Item | Status | Result |
|---|---|---|---|
| B1 | Loser map: from our own past trades (≤ fit year), find the conditions that hold most losing trades (regime, volatility, breadth, hour, coin) and veto them | queued | |
| B2 | Winner map: the conditions holding 80% of our winning trades; trade only those (subject to the 70% availability rule) | queued | |
| B3 | Per-coin efficiency: drop coins whose past win rate × average trade is negative | queued | |

## C. Reinforcement learning

| # | Item | Status | Result |
|---|---|---|---|
| C1 | Reward v1 (DD charged every dip) | dropped | made "flat" optimal (always-long −59%/episode) |
| C2 | Reward v2 (DD charged once per episode, ×0.1) | running | 49 h: 2026 −4.1%, DD 30%; releases 13–20 identical |
| C3 | Stagnation ladder (entropy ↑, lr ↑, fresh weights) | adopted | applied by the 8-hourly review |
| C4 | RL as the exit manager: entries from the search champion, the policy only decides to hold, halve or close an open trade ("notice the market has turned against it") | queued | the operator's idea; smaller problem than full trading |
| C5 | Train ≤ 2024, select releases on 2025, so release choice is out of sample | idea | |
| C6 | Stronger end-of-episode DD price (0.3) once C4 runs | idea | |

## D. More data

| # | Item | Status | Result |
|---|---|---|---|
| D1 | Multi-timeframe views (1h/4h/1d/1w) of the coin and BTC | adopted | in `World.full()` |
| D2 | Lagged macro panel (8 columns) | adopted | in `World.full()` |
| D3 | Perpetual funding rates and open interest (crowding, leverage) | idea | needs a source with history to 2019 |
| D4 | Stablecoin supply / exchange net flows | idea | |
| D5 | Order-book imbalance / taker buy share | idea | taker share is in Binance klines |
| D6 | News | dropped for now | the operator: maybe not relevant |

## E. Process

| # | Item | Status | Result |
|---|---|---|---|
| E1 | 8-hourly review: health, RL ladder, search summary, event on the monitor | adopted 2026-10-08 | `review.py`, run by the watchdog |
| E2 | Report max profit AND optimal (profit vs drawdown) every review | adopted | |
