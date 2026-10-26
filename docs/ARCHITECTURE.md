# System 12: the BTC regime book

An architecture brief for external review. It covers what the system does, how we built it, how we test that it holds up, and what keeps it safe. Live numbers are on the main page.

## In one paragraph

System 12 reads the BTC trend once a day:

- **When the trend is up:** it holds BTC and ETH long.
- **When it turns down:** it holds a half-size short.
- **Position size:** a volatility target sets it, and two small rules manage exits and sizing.

It trades Binance USD-M perpetual futures on paper with $50,000, and it has no ability to place real orders. It is the lab's 12th system and its only active one. Eleven earlier approaches were measured and dropped.

## What we did

| phase | what we learned |
|---|---|
| Systems 01-05 (Aug 2026) | Rule grammars, 5-minute momentum, supervised ML, LLM-written rules and meta-labelling. None kept an edge after costs on unseen data |
| Systems 06-10 (Aug-Oct 2026) | Neural nets taught by a hindsight oracle, dip buying, residual momentum, a market "ledger" model, and RL exits. Several looked strong in research and then failed out of sample |
| System 11 (Oct 2026) | An honest-execution audit: point-in-time coin lists (delisted coins included), fills at the next bar, and realistic costs. It showed the earlier results came from survivor bias and execution shortcuts. A coin-ranking model added almost nothing over a simple BTC trend gate |
| System 12 (from 21 Oct 2026) | We kept what survived, the BTC trend regime, and added shorts in bear phases, volatility sizing, and two overlays found one hypothesis at a time |

The central lesson: in crypto, most of the result comes from when the book is in the market and how much it holds, not which coins it picks.

## How it works

| step | rule |
|---|---|
| data | BTC and ETH 4h and daily candles (Binance spot), plus perpetual funding (Binance USD-M), from public APIs. Only closed bars are used |
| regime | 20 frozen rules, each combining two BTC trend readings (for example 60-day momentum AND BTC above its 100-day average), each between 0 and 1. The book averages all 20 |
| long leg | BTC+ETH 50/50, sized to a 40% annual volatility target, in steps of 25% |
| short leg | when a rule reads bearish, a half-size short of BTC or BTC+ETH under the same volatility target |
| overlay 1 | trailing stop on shorts: cover once BTC rises 10% above its low since the short began |
| overlay 2 | convex trend sizing: the long leg is multiplied by (1 + BTC 30-day return / 0.4), clipped to between 0.5 and 2, with gross exposure capped at 100% |
| timing | daily signals are read at the last daily close before each 4h decision; a decision taken at a bar's close trades from the next bar |
| costs | 0.10% per side, plus square-root market impact for a $100k book, plus funding every bar |

The rules are deterministic. There are no random seeds and no model weights, so the same data always gives the same positions. The whole strategy is under 200 lines (`system12/strategy.py`), and the execution and cost model is in `system12/backtest.py`.

## How we make it consistent

We assume any good-looking result is luck until it survives the following checks.

| safeguard | what it does |
|---|---|
| walk-forward only | each year is traded with rules chosen only on earlier years. No reported year ever helped choose its own rules |
| 2026 is never used to choose | 2026 is the out-of-sample year, read but never optimised, and the live paper book is the final test |
| one hypothesis at a time | each idea is written down before it runs, tested against the frozen book, and adopted only if it wins out of sample |
| a bar that rises with every test | after n tests, a new idea must beat the book by a Sharpe margin of 0.05 + 0.03 × ln(n). Of 15,288 tested ideas, one overlay pair was adopted |
| train, validate, test | ideas are scored on 2021-23, must not lose on 2024-25, and 2026 is never looked at. A drawdown cap of 40% applies throughout |
| long-history check | the adopted overlays were re-tested on BTC from 2014 to 2020, years the search never saw: drawdown 42% → 32% |
| cross-asset check | the same logic on ETH, 2018-2026: 9 of 10 years positive |
| cost and funding stress | with funding charged on longs and costs doubled, the 2017-2026 BTC+ETH version stays positive in 9 of 10 years |
| no large searches | every big search we ran produced in-sample winners that failed walk-forward, so the method now forbids them |

### Record (each year traded with rules chosen on earlier years only)

| | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| System 12 (champion v6) | +148% | -13% | +48% | +25% | +9% |
| max drawdown in the year | 24% | 32% | 16% | 36% | 21% |
| BTC | +60% | -64% | +156% | +121% | -6% |

On long history, the BTC version of the same logic had one losing year (-1%) in 13 (2014-2026), with a 37% drawdown against BTC's 84%.

## How we keep it safe

| area | protection |
|---|---|
| money | paper only. The repository contains no order, wallet or exchange-key code, so it cannot trade |
| credentials | none in the repository. The deploy token for the web page lives in a file on the operator's machine, outside git, and is never printed or committed |
| data | public market data only. No private feeds, no personal data |
| look-ahead | every signal is lagged one bar; tests check that changing the future never changes a past decision |
| reproducibility | the rules are deterministic, the selection is frozen in a versioned file (`system12/selection.json`), and the record file is checked against this document by the tests |
| verification | at the 2026-10-25 rewrite, the new code was checked bar by bar against the original engine. Positions match exactly on every bar since 2023-06; earlier differences come from days with incomplete data in the old store |
| risk in the book | volatility targeting, gross exposure capped at 100%, short size at half, and a trailing stop on shorts |
| change control | every change goes through git with tests, lint and format checks; every action is logged in `docs/RESULTS.md` |

## Known limits

- **It is a trend system.** It earns little in sideways markets: 2025 made +9%, and 2026 so far makes a few percent.
- **Drawdowns are deep.** A single year reached 36%, and the 2021-2025 chain of the base book reached 42%.
- **Two assets, one idea.** There is no diversification across strategies.
- **The 2022 crash.** The regime turns late in fast crashes, and every faster exit we tried cost more in other years.
- **Short squeeze risk.** Short sizes above 50% were never tested.
- **The paper record is short:** days, not years.

## Questions we would like reviewers to challenge

1. Is a 20-rule average enough protection against having chosen the rules from 75,504 candidates?
2. Is the rising adoption bar (0.05 + 0.03 × ln n) strict enough after 15,288 tests?
3. What would you add for sideways markets that is not simply another trend filter?
4. Is a 36-42% drawdown acceptable for this return profile, and what would you use to reduce it?

## Operating

| what | how |
|---|---|
| paper book | `python -m system12.paper` runs every 4h (Windows task `system12-paper`): $50,000 since 2026-10-22 16:00 UTC |
| backtest | `python -m system12.backtest` prints the frozen system's yearly results |
| pages | `python -m system12.web --deploy` builds and publishes the live page and this document |
| tests | `python -m pytest tests` |
| code | https://github.com/meshkore/sample-cluster-crypto-algo-open-agents-development |
