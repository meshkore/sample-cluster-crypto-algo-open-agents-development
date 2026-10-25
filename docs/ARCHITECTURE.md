# System 12: the BTC regime book

System 12 is the lab's only active system. It reads the BTC trend once a day:

- **Bullish:** it holds BTC and ETH long.
- **Bearish:** it holds a half-size short.

It runs on Binance USD-M perpetual futures, and it trades on paper only, never with real money.

## The idea

In crypto, most of a book's result comes from when it is in the market and how much it holds. Which coins it holds matters far less.

Eleven earlier systems tried to pick coins, learn price shapes or rank the market:

- None of them survived honest execution.
- The BTC trend did survive: point-in-time coin lists, fills at the next bar, real costs.

## Data

| input | source | use |
|---|---|---|
| BTC and ETH, 4h and daily candles | Binance spot, public API | signals, volatility, prices |
| BTC and ETH funding | Binance USD-M, public API | charged to every open position |

The data is cached outside the repository (`QUANTLAB_DATA`). Bars are stamped at their close, and only closed bars are used.

## The rules

**1. Twenty regime rules.** Each rule is a BTC trend reading between 0 and 1. The book is the average of 20 frozen configurations.

| part | what it does |
|---|---|
| regime | two BTC rules combined. Examples: 60-day momentum AND BTC above its 100-day average; 14-day AND 30-day momentum; moving-average ratio rules |
| long leg | BTC+ETH 50/50 while the regime is on |
| sizing | 40% annual volatility target, exposure in steps of 25% |
| short leg | when the regime reads 0 (or below 0.5), a half-size short of BTC or BTC+ETH, under the same volatility target |

**2. Two overlays.** Both were adopted out of sample by the hypothesis loop (champion v6, G00233).

| overlay | what it does |
|---|---|
| trailing stop on shorts | it covers the short once BTC rises 10% above its low since the short began |
| convex trend sizing | it multiplies the long leg by (1 + BTC 30-day return / 0.4), clipped to between 0.5 and 2, with gross exposure capped at 100% |

**3. Timing.**

- Daily signals are read at the last daily close before each 4h decision.
- A decision taken at a 4h close trades from the next bar.

**4. Costs.** Each trade pays 0.10% per side plus square-root impact for a $100k book. Funding is charged every bar, and a short receives positive funding.

There are no seeds and no fitted models, so every run gives the same result. The code is in `system12/strategy.py`, about 250 lines.

## How it was chosen

- **Walk-forward.** Each year N is traded with configurations chosen only on 2019 to N-1.
- **The 20 members.** They are the best 20 of 75,504 configurations (regime × basket × sizing × short rule), ranked on 2019-2025.
- **The overlays.** They were chosen by a loop that tested 15,288 hypotheses one at a time against the frozen book. A candidate was adopted only if it beat the book out of sample and passed a 2014-2020 check on BTC alone.
- **2026 is never used to choose.** It is the out-of-sample year, and the paper book is the live test.

## Record

Each year below was traded with rules chosen on earlier years only.

| | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| System 12 (champion v6) | +148% | -13% | +48% | +25% | +9% |
| max drawdown in the year | 24% | 32% | 16% | 36% | 21% |
| BTC | +60% | -64% | +156% | +121% | -6% |

The live page shows 2026 to date and the paper book.

## Known limits

- **It is a trend system.** It earns little in sideways years: 2025 made +9%, and 2026 so far makes a few percent.
- **Drawdowns are deep.** A single year reached 36%, and the 2021-2025 chain without the overlays reached 42%.
- **Two assets, one idea.** There is no diversification across strategies.
- **The 2022 crash.** The regime flips late in fast crashes. Every faster exit tested so far cost more in the other years.
- **Shorts carry squeeze risk.** Short sizes above 50% were never tested.

## What did not work (Systems 01-11 and System 12's own tests)

| tried | why it was dropped |
|---|---|
| rule grammars, 5-minute momentum, supervised ML, LLM-written rules, meta-labels (Systems 01-05) | no edge after costs, or no edge out of sample |
| oracle-taught 15m neural net (System 06) | walk-forward exams 2023 +3%, 2024 +22%, 2025 -6.5%, on a survivor universe |
| capitulation dip buying (System 07) | never held up on an unseen year |
| residual momentum long/short (System 08) | positive in 8 of 8 research years, then -26% in 2026 |
| participant ledger (System 09) | the research IC of +0.14 fell to -0.06 out of sample |
| conditions plus an RL exit (System 10) | on point-in-time coins with honest costs, -12% to -21% |
| cross-sectional coin ranking (System 11) | the edge was the BTC regime, not the ranking; System 12 replaced it |
| bigger searches, altcoin overlays, macro filters, 593 published strategies, hourly event rules, neural nets on hourly perps | none beat this book walk-forward |

The full record of every system, test and model is archived outside this repository.

## Operating

| what | how |
|---|---|
| paper book | `python -m system12.paper`, every 4h (Windows task `system12-paper`): $50,000 since 2026-10-22 16:00 UTC |
| page | `python -m system12.publish --deploy` builds and publishes this page and the live view |
| tests | `python -m pytest tests` |
| real money | none. This repository has no order or exchange-key code |
