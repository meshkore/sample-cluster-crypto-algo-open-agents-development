# System 12 - the BTC regime system (ACTIVE since 2026-10-21)

Code, runs and operating detail: `research/system12/README.md`. Predecessor: System 11 (`system011_xs_ranking_pit`).
External review request (round 4): `research/system12/BRIEF.md`, public at https://quantlab-architecture.rjj.workers.dev/architecture.
Earlier refusals worth reading first: `system006_oracle_net_15m/docs/SUMMARY.md` and `system011_xs_ranking_pit/docs/SUMMARY.md`.

## 1. Hypothesis

Technical analysis on the whole market (when to be in, how much, and when to be short) carries the edge in crypto; which coins to hold is second order. A BTC-trend regime with long BTC+ETH in bull phases and a half short in bear phases beats both buy-and-hold and coin selection.

## 2. What it is

- **Regime:** BTC above its 50-200-day averages and rising over 14-90 days, several rules combined.
- **Bullish:** long BTC+ETH.
- **Bearish:** a half-size short of BTC/ETH on USD-M perpetuals.
- **Sizing:** a 40% volatility target, exposure in steps of 25%.
- **The book:** the average of 20 combinations, chosen walk-forward from 75,504 (484 regimes x 4 baskets x 3 sizings x 13 short rules).
- **Data:** point-in-time top-14 lists, daily signals read at the last close before each 4h decision.
- **Costs:** 0.10%/side plus impact, funding charged.
- **Paper:** $50k since 2026-10-21 16:00 UTC.

## 3. What helped

| change | measured effect | evidence |
|---|---|---|
| Regime instead of coin ranking | the plain BTC-gated basket matched System 11 at equal risk | Classics 11 |
| Short in bear regimes (perps) instead of cash | walk-forward 2025 +9.7% (long-only -5%), 2026 +5.9% (long-only +0.7%) | `research/system12/out_ls` vs `out` |
| BTC+ETH as the basket | chosen by 19 of the 20 configurations; the coin baskets lost in 2022 and 2025 | `out_ls/results.json` |
| 40% volatility target | in-sample DD 20% vs 35-60% without it | robustness grid |
| Averaging 20 configurations | smoother than the single best: 2026 +5.9% vs -1.7% | walk-forward |

| Convex trend sizing + trailing stop on shorts (G00233, champion v6) | 12-year walk-forward on BTC daily: 12 of 13 years positive (only 2022 -1%); BTC+ETH 50/50 2017-26 with the 9 settings averaged: 9/10 positive, Sharpe 1.44 -> 1.67, survives funding + double costs (1.50) | `research/system12/robust/LAB14.md`, `lab14.py`, RESULTS log 2026-10-23 |

## 4. What hurt

| change | measured effect | evidence |
|---|---|---|
| Long-only regime search | walk-forward 2025 -5%, 2026 +0.7%; worse than System 11 in bear years | `research/system12/out` |
| A bigger search (48 signals: RSI, Bollinger, funding, macro, Fear & Greed...) | walk-forward 2026 -15% after 14,000 configs: more false winners | `lab12`, stopped |
| 150/200-day averages alone | positive in 5-6 of 8 years vs 7-8 for 50/100-day | robustness grid |
| Choosing on one year (2020 chosen on 2019) | -49% | walk-forward 2020 |
| Full-size shorts without a volatility target | drawdowns of 57-84% | robustness grid |
| Altcoin overlays (alt season, breadth, ETH/BTC, 2x alts; H019-H026) | all lose walk-forward: learned in 2020-21, they cost 2022-23 (2x alts: 2022 -59%) | `research/system12/hyp/ledger.jsonl` |
| Crash exit from the 20-day high (H001) | 2021 -46 pp, no year better | `hyp/ledger.jsonl` |

| Fed net-liquidity filter (catalogue, champion v5) | better every year 2021-26, but worse in 6 of 7 years 2014-2020 (2017 -4% vs +268%): an era effect | `research/system12/robust/LONG.md` |
| Stacking many loop adoptions (loop v1-v4) | in-sample 2021-25 up to +79%/yr, 2026 test -12% to -23%: selection luck | `research/system12/hyp_v1..v4/` |
| Market phases, cycle position, MVRV, DVOL, M2, stablecoins, catalogue averages, 14-coin trend, pre-signal candle state, decision-tree second layer | none survives walk-forward against the book | RESULTS log 2026-10-22 |
| Published retail strategies (catalogue, 593 tested) | 539 of 593 fail alone; the 21-23 UTC effect dies at taker costs | `research/system12/catalog/CATALOG.md`, `robust/HOURLY.md` |

## 5. What is still open

- **Champion v6 on paper** (`research/system12/paper_champion/`, from 2026-10-22): the 12-year evidence says the convex sizing + short trail are robust; weeks of paper are the next test. The trail level is a 2022-vs-2026 trade-off (task 16); averaging the 9 settings removes the choice (task 17).

- **The hypothesis loop** (`research/system12/hyp12.py`, since 2026-10-21): candidate champion H006 (ETH 75% of the long leg), not on paper; see `hyp/status.json`.
- **2022 (-23% walk-forward).** The regime flips too late in a crash: faster exits, volatility breaks, funding.
- **Short sizing and squeeze risk.** Untested beyond 25/50/100%.
- **A coin ranking inside the regime.** System 11's net was never tested this way.
- **Two project rules conflict with this system.** The operator decides: "long-only software" (it shorts on paper, approved 2026-10-21) and "abort at 25% drawdown" (the walk-forward chain reached 42%).

## 6. Rules learned

- One written hypothesis at a time, tested walk-forward against the frozen book; adopt only if it wins out of sample.
- No mass searches: the honest result gets worse as the search grows.
- The paper book runs untouched; it is the real test.
- 2026 is read, never used to choose.
