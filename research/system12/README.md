# System 12 - the BTC regime system (the ONLY active system)

Opened 2026-10-21. Paper-traded with $50,000 from 2026-10-21 16:00 UTC. Nothing else is being developed.

## What it is

Technical analysis on the whole market, not on single coins:
- **When the regime is bullish:** long BTC+ETH. Bullish means BTC rising over 14-90 days and above its 50-200-day average; several rules are combined.
- **When it turns bearish:** a half-size SHORT of BTC/ETH on USD-M perpetuals, instead of cash.
- **Sizing:** a 40% volatility target, with exposure in steps of 25%.

The book is the average of 20 rule combinations. Each was chosen by an exhaustive walk-forward search: 75,504 configurations, ranked by the law below on 2019-2025 only. The list is frozen in `paper/selection.json`.

## Why it exists (the one-paragraph history)

System 11 was a neural net ranking the top-14 coins. It earned about +30%/yr on 2020-25 but +1.7% in 2026.

Three days of honest attempts to improve it all failed walk-forward:
- bigger size;
- price stops and exits;
- 4,500 filter ideas against a placebo;
- Bayesian searches;
- 16 published strategies.

The decisive finding: "all coins, equal weight, while BTC > its 100-day average" earned about what System 11 earned at equal risk. The ranking net added almost nothing; the edge is the BTC regime. Hence System 12.

## Results (each year traded with the 20 configurations chosen ONLY on the years before it)

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 YTD (forward) |
|---|---|---|---|---|---|---|
| System 12 | +115% | -23% | +35% | +18% | +9.7% | +5.9% (DD 13%) |
| System 11 | +96% | -12% | +38% | +19% | +7.8% | +1.7% |
| BTC | +60% | -64% | +156% | +121% | -6% | -5% |

Notes:
- **2020** was chosen on 2019 alone, with four months of perpetuals. It reads -49% and is not meaningful.
- **Drawdown:** max DD over the 2021-2025 chain is 42%.
- **The frozen book** (chosen on 2019-2025): in-sample 2020-25 positive every year, DD 20%; 2026 is out of sample.
- **Sources:** `out_ls/REPORT.md`, `out_ls/results.json`, `out_ls/history_doc.json`.

## What runs

| Windows task | every | runs | writes |
|---|---|---|---|
| `system12-paper` | 4 h | `run_paper.ps1` -> `paper12.py`, then `system12_doc.py` | `paper/state.json`, `paper/decisions.jsonl` (audit), `out_ls/history_doc.json`, `lab/trades*.json` (page) |

- **Live page:** Training and Trades tabs (`#/live`) of https://quantlab-public-mirror.rjj.workers.dev. Pushed by `research/system06/preview/cf_pusher.py`, kept alive by the `system06-watchdog` task. The frontend is `research/system06/preview/dashboard.html`; the data comes from `mock_server._v2_live()`.
- **Paper rules:** decide at a 4h close and fill at the next bar; 0.10%/side plus impact; funding charged. The rules are causal, so every run recomputes the book from the start on closed bars only.

## Files

| file | role |
|---|---|
| `system12.py` | step 1: long-only search (regime x basket x vol target), 13,552 configs - superseded by step 2 |
| `system12_ls.py` | step 2: long + short on perps, 75,504 configs, 3 parallel chunks + `--merge` - **this defined the system** |
| `paper12.py` | the paper book (frozen selection, $50k) |
| `gen12.py` | the generator: when the written queue is empty, stacks of 1-3 pieces (32 entries, exits, stops, take-profits, sizing, shorts, alts) - singles, then pairs, then triples biased toward pieces that helped. Stored in `hyp/generated.jsonl` before they run; morning read `hyp/REPORT.md` |
| `hyp12.py`, `hypotheses12.py`, `run_hyp.ps1` | the hypothesis loop (task `system12-hyp`, every 10 min keeps `--loop` alive; brake `hyp/STOP`). Ledger `hyp/ledger.jsonl`, champion `hyp/champion.json`, page `hyp/status.json` |
| `paper12c.py` | the CHAMPION paper book: $50k from 2026-10-22 08:00 UTC, frozen snapshot of the loop's champion (H006 + G00008) in `paper_champion/selection.json`; runs in `run_paper.ps1` after the frozen book |
| `system12_doc.py`, `trades12.py` | the page's documents (year-by-year chain, 2026 trades) |
| `lab12.py`, `controller12.py`, `run_lab.ps1` | a bigger random search (48 signals). STOPPED 2026-10-21 (`lab/STOP`, task `system12-lab` disabled): its first walk-forward was WORSE (2026 -15%). Bigger searches find more false winners. Kept for reference only |

## Technical debt the next agent should know

- **Dependencies on System 11.** System 12 imports System 11 code from `research/plan_v2/`:
  - `history_v2.world()`: the point-in-time data, costs and funding;
  - `classics11.Ctx` and `bayes11` helpers;
  - `rocket11/cache/base.npz`: only for the unused "System 11 model picks" basket.

  Do not move or delete `research/plan_v2/` until System 12 has its own small data module.
- **PYTHONPATH** (Git Bash, from the repo root, `R=$(pwd -W)`): `R/research/system12;R/research/plan_v2;R/trading-system;R/trading-system/systems;R/research/system10/tools;R/backtester;R/live-trading`.
- **Two project rules conflict with System 12** (CLAUDE.md "Project rules"). Both are the operator's decision; do not change them yourself:
  - "long-only software": System 12 shorts on paper. The operator approved it ("go", 2026-10-21) but the rule text was not updated.
  - "abort at 25% drawdown": the walk-forward chain reached 42%.

## How to improve it (the method the operator agreed, 2026-10-21)

**Running since 2026-10-21 as a loop** (operator: "hypothesis 1, 2, 3 ... up to 1000, without stopping"):
- each hypothesis is appended to `hypotheses12.py` with its text BEFORE it runs; never edit one that ran;
- its parameter (or "off") is chosen on years < N, read on N, against the champion (frozen book + adopted overlays);
- adopted only if it beats the champion in >= 4 of 5 years (2021-25), by a mean gain >= 1 pp + 0.5 pp x ln(n tested), with the 2021-25 chain DD at most 40% (operator 2026-10-22);
- an adopted champion is a CANDIDATE: the paper book stays frozen until the operator moves it.

- **One hypothesis at a time,** written down BEFORE it is tested. Examples: the short size, the regime exit rule, ETH vs BTC weight.
- **Each tested walk-forward** (chosen on years < N, read on N) against the frozen book.
- **Adopted only if it wins out of sample.**
- **No mass searches.** Every one this lab ran (Bayes 11, Rocket 11, lab12) produced in-sample winners that did not survive walk-forward.
- **2026 is never used to choose.** The paper book is the real test: weeks and months, untouched.
