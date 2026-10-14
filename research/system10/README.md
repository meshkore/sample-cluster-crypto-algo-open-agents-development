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

Paper book: release 31, $50,000 from 2026-10-13 20:00 UTC (`paper/`, Trading tab).

## What runs (watchdog, 24/7)

| job | module | does |
|---|---|---|
| w1–w4 | `search` | condition search, research bars ≤ 2025 only; publishes `releases/` |
| evaluator | `evaluator` | reads the newest release on 2026 every hour |
| paper | `paper` | books the pinned release on live bars; freezes every bar's inputs |
| status | `status` | `rnd/live_status.json` every 10 s for the Live tab |
| review | `review` + `pivots` | health every 15 min, daily stall gate (EXPLORE after 3 days), 8-h and weekly reports |

Switchboard: `jobs.json` (false = stopped, not relaunched). Brake: `STOP_S10`. One restart:
create `RESTART_<job>`. Ledgers: `rnd/search_trials.jsonl`, `rnd/events.jsonl`, `rnd/reviews.jsonl`,
`rnd/weekly/`. Ideas not yet tried: `IMPROVEMENTS.md`.

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

Everything deleted on 10-14 is recoverable: `git checkout s10-before-cleanup -- <path>`.
