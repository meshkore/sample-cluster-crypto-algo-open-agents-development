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
| A1 | Drawdown cap: no year above 25% max DD is eligible | adopted 2026-10-08 | release 20 (DD 45–53%) no longer qualifies; release 27 meets it: every year 2022-25 positive (worst +2.3%), CAGR +8.9%, DD 24.5% |
| A2 | Account stop: close all and pause 3 days when the book is X below its peak (8/12/16/20%) | dropped | does not bound the year: the legs add up (8% stop, 56% year DD) |
| A2b | Drawdown-scaled stakes: x max(0.25, 1 - DD/L) from the year's true peak | adopted | with 5-8 slots it is what brought DD under 25% |
| A3 | Tighter per-trade stop (5/8/12% vs 16.3%) | running | search lever `stop` |
| A4 | More, smaller positions (5 or 8 slots instead of 3) | adopted | 8 slots: worst year -2% -> +4%, DD 51% -> 41% on release 20's signals |
| A5 | Volatility targeting: stake x clip(k x ref vol / coin's 1-day vol, 0.25, 1), k in 0.75/1/1.5 | running 2026-10-10 | search lever `vol_target` |
| A6 | Correlation limit: at most N positions in coins moving together | idea | |
| A7 | Equity-curve filter: halve stakes while the account is below its own 30-day average | idea | |

## B. Pareto filters: trade only where we win

| # | Item | Status | Result |
|---|---|---|---|
| B1 | Loser map: from our own past trades (3 prior years), veto conditions (regime x vol tercile x breadth) with >= 20 trades and a negative mean | running 2026-10-10 | search lever `veto`; first 4 trials: on release 27 worst year +2.3% -> +0.6%, CAGR +8.9% -> +5.4% - hurts so far |
| B2 | Winner map: the conditions holding 80% of our winning trades; trade only those (subject to the 70% availability rule) | queued | |
| B3 | Per-coin efficiency: drop coins with >= 20 past trades and a negative mean | running | part of `veto` |

## C. Reinforcement learning and the trader

The operator's architecture (2026-10-10): a signal model that emits continuous buy/sell
strength every candle, and a trader that opens progressively while the signal holds and
sells a piece or a lot as it weakens. Everything before C7 narrowed the trader to binary
entries plus "close early", which left RL nothing to add over the supervised exit.


| # | Item | Status | Result |
|---|---|---|---|
| C1 | Reward v1 (DD charged every dip) | dropped | made "flat" optimal (always-long −59%/episode) |
| C2 | Full-trader PPO, reward v2 (DD charged once per episode, ×0.1) | dropped 2026-10-09 | 56 h and two ladder resets: 2026 −4.1%, DD 30%; never beat the rules. Replaced by C4 |
| C3 | Stagnation ladder (entropy ↑, lr ↑, fresh weights) | adopted | applied by the 8-hourly review |
| C4 | **retired 2026-10-10** - RL as the position manager (releases 1-3: from scratch, then residual; all lost to the rule out of sample, 2024 +8.9% / -0.1% vs +42.3%; v2: 12 columns + 24 h re-entry pause; v3: return-only reward, release 5: 2024 +16% vs +42.3%, 2025 -4.2%, 2026 -4.2%): entries from the best release, the policy decides hold/close every 4 h ("notice the market has turned against it") | running 2026-10-09 | `manager.py`; trains 2020-2024, judged on 2025 (out of sample) and 2026 against the release's own exit (2024 bar: +42%, DD 23%) |
| C5 | Train ≤ 2024, select releases on 2025, so release choice is out of sample | idea | |
| C6 | Stronger end-of-episode DD price (0.3) once C4 runs | dropped | C4 retired |
| C7 | Signal-strength trader, deterministic: stake = clip(forecast / k, 0.25, 1); every 4 h add a quarter slot while forecast >= +0.6%, halve when < 0 | running 2026-10-10 | search levers `size_signal`, `scale_in`; the gate for C8 |
| C8 | RL trader: actions -1 / -1/2 / 0 / +1/2 / +1 slot from the continuous signal, the trade and the account; only if C7 shows the magnitude carries information | queued | GPU is free for it |
| C9 | Short side in the falling regime (perps, funding paid) | idea | 2022 would be the test; a different venue and cost model |

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
