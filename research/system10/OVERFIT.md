# System 10 - overfitting measures (audit 2.2)

Code: `system010_conditioned_rl/overfit.py`, from the trial ledger only (no fits). Runs in
review.py's 8-hour pass -> `rnd/overfit.json`; weekly report "Overfitting"; Live tab `main.overfit`.

- **Nested curve** (the expected performance): for N = 2023..2025 the selection law picks on
  years < N only (eligibility too: DD cap, trades, availability, guards), then N is read.
  The max-over-trials champion is a diagnostic. `nested_confirm`: only rows run on both seed
  sets, chosen on the weaker set, read on the confirm set.
- **PBO** by CSCV (Bailey, Borwein, Lopez de Prado, Zhu 2017) over the eligible distinct
  trials. Yearly law score now (4 years = 6 splits: coarse). Trial rows carry `monthly` from
  2026-10-15; from 50 such rows PBO switches to monthly Sharpe, 16 blocks.
- **DSR** (Bailey & Lopez de Prado 2014) of the champion given the trials; annual now
  (4 points: coarse), monthly once rows carry months.
- **Gate**: `search.overfit_refusal()` - no new release while PBO > 0.5; the newest existing
  release stays current. Missing or > 36 h old file never blocks.

First reading, 2026-10-15 (1,512 eligible distinct trials):

| 2023-25 | 2023 | 2024 | 2025 | CAGR | worst | max yearly DD |
|---|---|---|---|---|---|---|
| chosen on the past | +21.7% | +88.5% | +27.8% | +43.1% | +21.7% | 30.1% |
| champion (release 34) | +19.4% | +80.4% | +35.2% | +42.8% | +19.4% | 24.4% |
| chosen on the past, confirm seeds | +11.4% | +59.7% | +16.1% | +27.3% | +11.4% | 23.7% |
| champion, confirm seeds | +12.0% | +47.3% | +25.8% | +27.6% | +12.0% | 24.6% |

PBO 0.17 (yearly) -> gate open. DSR 0.05 (PSR vs 0: 0.97): after 1,512 trials the
champion's Sharpe is not distinguishable from the best of noise. Caveat: the ledger was walked
toward configurations good on all of 2022-25, so the nested curve is still an upper bound.
