# System 10 — read this first

**One line of work: the condition search + signal-strength sizing ("main line").** Everything
else was tried and closed (decision log below). Code: `trading-system/systems/system010_conditioned_rl/`
(the package name is historical — there is no RL in it any more).

## What it is

Per 15-minute bar, on 14 coins: a **market gate** (BTC vs its N-day average + breadth) decides
whether trading is allowed; an **AI selector** (small nets, 4 seeds) picks which opportunities to
take; an **AI exit** forecasts the next day's return — buy when ≥ +0.3%, sell when < −0.3%, and the
forecast's size sets the stake. The **book** (`tools/conditions.py: book_year`) applies the money
management: slots, stop, trailing stop, max hold, drawdown-scaled stakes.

The search tries configurations of all of that, walk-forward: models fitted on years < N, judged on
N ∈ 2022–2025. Score = worst year + 0.1 × CAGR. Eligible only if it can trade ≥ 70% of days (gaps ≤ 40
days) and **max drawdown ≤ 25% every year**. A new best (confirmed on a second seed set) becomes a
numbered **release**. 2026 is forward-only: read, never used to choose.

## Where we are (2026-10-14)

| | worst year | CAGR 22–25 | max DD | 2026 forward |
|---|---|---|---|---|
| **release 31** (optimal, live) | +10.3% | +30.8% | 24.7% | +22.4%, DD 17.3% |
| max profit | +7.6% | +35.1% | 23.7% | — |

Paper book: release 34 since 2026-10-15 15:09 UTC (31 -> 33 -> 43 -> 34, hot swaps), $50,000 from 2026-10-13 20:00 UTC (`paper/`, Trading tab).

**Approach audit 2026-10-15: `AUDIT_2026-10-15.md`** - two certain defects (survivor-selected
universe, max-of-17,951-trials selection), what data would and would not help, no case for more GPUs.
**Book-layer audit + plan: `AUDIT_BOOK_2026-10-15.md`** - money management is a separate layer already;
plan: freeze signals, nested lever choice, vol targeting / mean-variance sizing / meta sizer A/Bs, measured costs.

## Book layer on frozen signals (book audit, 2026-10-15)

Releases 31/34/43 share one signal set; only the book differs. `tools/book_lab.py` books it alone
(ledger `rnd/book_trials.jsonl`, 432-book grid). Nested = book chosen by the law on years < N, read N.

| book, 2022-25 | 2022 | 2023 | 2024 | 2025 | CAGR | worst | max DD | law |
|---|---|---|---|---|---|---|---|---|
| **nested (expected)** | +14.7% | +16.2% | +45.7% | +6.2% | +19.8% | +6.2% | 18.3% | 0.113 |
| release 31 | +29.1% | +17.5% | +47.8% | +30.6% | +30.8% | +17.5% | 22.6% | 0.226 |
| release 34 (champion) | +43.0% | +19.4% | +80.4% | +35.2% | +42.9% | +19.4% | 24.4% | 0.270 |
| release 43 | +9.2% | +16.2% | +105.5% | +79.5% | +47.1% | +9.2% | 20.0% | 0.272 |
| 43 + stop 12% + dd_scale 0.35 | +7.6% | +16.0% | +73.9% | +50.5% | +34.4% | +7.6% | 18.3% | 0.242 |
| grid max (diagnostic) | +26.2% | +18.2% | +81.0% | +62.0% | +44.6% | +18.2% | 19.7% | 0.304 |

2020-21 (not judged by the search): release books reach 39-49% DD. `rnd/book_nested.json`, `rnd/book_baseline.json`.

## What runs (watchdog, 24/7)

| job | module | does |
|---|---|---|
| w1–w4 | `search` | condition search, research bars ≤ 2025 only; publishes `releases/` |
| evaluator | `evaluator` | reads the newest release on 2026 every hour |
| paper | `paper` | books the pinned release on live bars; freezes every bar's inputs |
| status | `status` | `rnd/live_status.json` every 10 s for the Live tab |
| review | `review` + `pivots` | health every 15 min, daily stall gate (EXPLORE after 3 days) and `challengers` (`rnd/challengers.json`), 8-h and weekly reports |

Switchboard: `jobs.json` (false = stopped, not relaunched). Brake: `STOP_S10`. One restart:
create `RESTART_<job>`. Ledgers: `rnd/search_trials.jsonl`, `rnd/events.jsonl`, `rnd/reviews.jsonl`,
`rnd/weekly/`. Ideas not yet tried: `IMPROVEMENTS.md`.
Book-lever A/B on cached release inputs: `tools/levers_study.py` → `rnd/levers_study.json`.

## Decision log — closed, do not re-propose without new evidence

| date | tried | result | decision |
|---|---|---|---|
| 09-27 | RL policy inside the oracle's "region" (clone → offline RL → PPO) | region too thin to trade; never beat the rules | replaced by the condition search |
| 10-08 | Full-trader PPO, 56 h | 2026 −4%, DD 30% | dropped |
| 10-08 | Account stop (close all at −X%) | legs add up (8% stop → 56% year DD) | dropped; drawdown-scaled stakes adopted |
| 10-08 | More, smaller positions (5–8 slots) | DD 51% → 41%, worst year −2% → +4% | adopted |
| 10-09 | RL position manager (hold/close every 4 h) | lost to the rule exit out of sample (2024 +16% vs +42%) | retired |
| 10-10 | Signal-strength sizing (stake ∝ forecast) | 2025 DD 25% → 11–15% at equal return | adopted — it is what made DD ≤ 25% reachable |
| 10-10 | Pareto veto of losing conditions | worst year +2.3% → +0.6% | stays a search lever, rarely wins |
| 10-10 | RL sizer v4 | added trading rules, no gain | retired |
| 10-10 | GPU forecaster ensemble (55 variants, IC ≈ 0.04) | 42 search trials, none qualified | retired 10-14 |
| 10-11 | RL decision engine v1–v3 (long/flat/short, PPO, 14 → 47 coins) | 2025 swings −26%..+14% between releases vs trend +15% | retired 10-14 |
| 10-14 | Focus | only the main line wins every unseen year and 2026 | **all work on the main line** |
| 10-14 | Market-health guard (`HEALTH.md`) | market halts cost return (the release buys crashes); book losing-streak flatten won 2020–25 (CAGR +38% vs +26%, DD 28% vs 39%) but 2026 +9% vs +22% | indicator live, guard advisory only |
| 10-14 | Correlation cap (`corr_cap`, ≤ N held coins with 30-d corr > ρ) | best 3@0.9: 22–25 score +0.206 = release; tight caps cut 2020–21 DD but cost return | search lever, not adopted |
| 10-14 | Equity-curve filter (`eq_filter`, stakes ×0.75 below N-day avg) | every setting below the release (best 10 d: CAGR +29.5% vs +30.8%) | search lever, not adopted |
| 10-14 | Win-rate levers (`min_edge`, `take_profit`, `breakeven`) | edge 0.004: win 0.563 → 0.569 at equal score; TP/breakeven raise win rate only by cutting return | search levers, not adopted |
| 10-14 | Momentum boost (`mom_rank`: 2× stake on top-k coins by 60/90-d return) | top-5/60 d: 22–25 CAGR +41.5% vs +30.8%, DD 24.1% vs 22.6%, worst year +19.8% vs +17.5%; 2020–21 slightly worse; 2026 +47.5%/DD 16.4% vs +22.4%/17.3%. Same exposure on every coin breaks the 25% cap; filters (top-k only) lose | **in the search, probed first**; release needs the workers' confirm |
| 10-14 | Simple challengers, same candles and costs (BTC hold, equal-weight, BTC 50/100/200-day trend, top-3/5 momentum, vol-targeted trend) | none beats release 31 on 2022-25 worst year; momentum CAGR up to +55% but DD 54-58% | re-checked daily, event if one wins |
| 10-15 | Selection law | old score (worst + 0.10 × CAGR) let one boom year win (release 38: 17/18/92/42) | **new law**: 0.5 × floor of the 3 worst years + 0.5 × recent years weighted 1:2:3:4 (each capped +50%) − 0.25 × max DD; unconfirmed leaders re-run first |
| 10-15 | Overfitting (audit 2.2): nested selection, PBO (CSCV), Deflated Sharpe from the ledger (`OVERFIT.md`) | chosen-on-the-past 2023-25 CAGR +43.1%, worst +21.7% vs champion +42.8% / +19.4%; PBO 0.17 (yearly, coarse); DSR 0.05 | **nested curve is the expected performance**; no release while PBO > 0.5 |
| 10-15 | Point-in-time universe (`PIT.md`: top 14 by turnover on 31 Dec N-1, delisted included) | r31 2022-25: 0 trades / +7.4 / +4.8 / +42.9%, DD 30.6%, 2026 -10.6% (vs +29/+18/+48/+31, +22.3% on today's 14); r34 and r43 the same pattern | **survivorship confirmed**: no release eligible on PIT; opt-in only, search unchanged pending review |

Everything deleted on 10-14 is recoverable: `git checkout s10-before-cleanup -- <path>`.
