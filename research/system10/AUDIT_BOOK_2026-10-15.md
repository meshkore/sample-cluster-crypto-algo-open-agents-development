# System 10 — book layer audit and plan (2026-10-15)

Second audit, asked for by the operator after `AUDIT_2026-10-15.md` (signal layer; being coded).
Scope: the **money-management layer** only — `tools/conditions.py: book_year` — sizing, scaling
in and out, exits, risk, execution. The signal layer is treated as frozen input throughout.
Design document; no code until the operator says so.

## 1. What the book does today and how it is chosen

| decision | rule in `book_year` | lever(s) |
|---|---|---|
| how many positions | N equal slots of the book's current value | `slots` (3/5/8) |
| entry size | slot × clip(forecast / `size_signal`, 0.25, 1) × regime (0.75 when BTC < MA) × max(0.25, 1 − DD / `dd_scale`) × momentum (2× top-k) × equity filter | `size_signal`, `size_down`, `dd_scale`, `mom_rank/days/in/out`, `eq_filter/cut`, `vol_target` (per coin) |
| during the life | every 4 h: add a quarter slot while forecast ≥ +0.6% (to one slot), halve when forecast < 0 | `scale_in`; thresholds `add_above`/`trim_below` are constants, never searched |
| exit | first of: stop, take profit, breakeven stop, trailing stop (06's), time cap, forecast < −0.3% after 4 h | `stop`, `take_profit`, `breakeven`, `horizon` |
| account-level | drawdown-scaled stakes; optional account brake; optional correlation cap; advisory health guard | `dd_scale`, `book_stop`, `corr_cap/rho`, guard |
| costs | 0.30% round trip, fill at the 15-minute close, no impact, no partial fills | constant `ROUND_TRIP` |

Chosen by: the same search and the same law as the signals, i.e. the max over ~18k joint
trials. `levers_study.py` (10-14) was the first book-only A/B, on release 31's cached signals.

**Findings**
1. The book is already a separate, deterministic layer with a clean interface (masks, keep,
   strength, size per bar → fills). Nothing structural is missing.
2. Its levers are selected jointly with the signals through the max-over-trials (signal audit
   §2.2). Release 43 shows the cost: it dropped `stop` 12% and `dd_scale` — the two levers the
   decision log credits with the 25% cap — because a configuration without them scored 0.001
   higher. The cap on release 43 is therefore in-sample only.
3. Sizing reads the forecast's **mean** and ignores its **uncertainty** and the coin's variance.
   Every published sizing rule (Kelly, vol targeting) sizes on mean / variance; ours is mean only,
   then a per-coin vol clip as an optional lever.
4. Exposure is targeted per coin, never for the whole book: eight correlated longs in one BTC
   move are one bet (the corr cap exists but never won under the joint selection).
5. The scaling-in thresholds (+0.6% add, < 0 trim) are hard-coded constants from 10-10.
6. Costs are a constant. Real slippage on BingX is unmeasured; the mirror runs in shadow and can
   measure it.

## 2. What the literature supports (and what it does not)

| idea | evidence | expected effect on this book |
|---|---|---|
| Portfolio volatility targeting | Moreira & Muir 2017 (JF); Harvey et al. 2018: higher Sharpe, lower DD for trend/momentum books, little for others | our book IS a momentum/trend book → DD down at equal or better return |
| Size on mean/variance (fractional Kelly) | Kelly 1956; MacLean, Thorp, Ziemba 2011: half-Kelly dominates full; sizing on mean alone over-bets high-variance names | stake ∝ forecast / σ² replaces ∝ forecast |
| Meta-labelling sizer | López de Prado 2018 ch. 3; 06's own A/B: drawdown reducer, not a return engine | DD down; return flat |
| Volatility-scaled stops / trails (ATR) | standard in trend literature (e.g. Clenow 2013) | fewer stops hit by noise in high-vol coins; untested here |
| Account stop / de-risking halts | our 10-08 and 10-14 results: legs add up; halts cost return | **closed**, not re-proposed |
| RL position manager | our 10-09 result: lost to the rule exit out of sample | **closed** |
| Limit orders / execution models | Almgren–Chriss 2000; at $50k on majors impact is small, on ACE/WLD-size coins it is not | correct the cost constant per coin; no alpha |

## 3. Plan

Each phase has a deliverable and an acceptance gate. All choices on ≤ 2025, nested (chosen on
< N, read N). 2026 is read once per adopted change, never to choose.

### Phase 0 — Freeze the signals, build the harness (≈ 1 day)
- Tool `tools/book_inputs.py`: cache any release's walk-forward signals per year 2020–2025
  (enter, keep, strength, size, closes) to `rnd/book_inputs_<release>.npz`. Generalises
  `health_study.load_inputs` (release 31 only).
- Tool `tools/book_lab.py`: book-only runs on a cached release; per year return, DD, trades,
  daily series; 21-day block bootstrap of the annual distribution (P(year ≥ target), p05) so a
  lever's effect is read against a confidence band, not a point.
- Baseline: releases 31 and 43 with their own books, and release 43 **with** stop 12% +
  dd_scale 0.35 restored (finding 2).
- Gate: the harness reproduces the release ledger rows to the fourth decimal.

### Phase 1 — Honest selection for the book (≈ 1 day)
- Nested lever choice: for each N in 2022–2025, choose the lever set on years < N by the
  operator's law, read N. Publish `rnd/book_nested.json` and a table in `README.md` next to the
  release table. This is the expected live performance of the book; the joint-max number
  becomes a diagnostic.
- Gate: nested curve computed for releases 31 and 43; its worst year and DD recorded.

### Phase 2 — Levers with evidence, one A/B each on frozen signals (≈ 1 week)
In order; each A/B nested, each must beat the incumbent book on the law in ≥ 3 of 4 years by
more than the bootstrap band and not raise max DD, else it goes to the decision log as closed.
1. **Portfolio vol targeting**: target annualised book vol V (search 20–40%); all new stakes ×
   clip(V / realised 20-day book vol, 0.25, 1.0). One lever `port_vol`.
2. **Mean/variance sizing**: stake ∝ forecast / σ²_coin(1d) normalised to the 2020 median, replacing
   stake ∝ forecast. Lever `size_kelly` (fraction, 0.25–0.5).
3. **Scaling-in thresholds searched**: `add_above` ∈ {0.3, 0.6, 1.0}%, `trim_below` ∈ {−0.3, 0, +0.3}%.
4. **ATR trail**: trail = k × ATR14 instead of 06's fixed %, k ∈ {2, 3, 4}.
5. **Meta-labelling sizer**: small net on years < N: P(trade closes > 0 | 44 features, forecast,
   regime, breadth); stake × p / p̄. Reference `system006_oracle_net_15m/modules/meta.py`.
   Expected: DD reducer. Adopt only if the law improves.
6. **Correlation cap revisited** under nested selection (it lost only under the joint max).

### Phase 3 — Execution realism (needs ≥ 2 weeks of BingX shadow fills)
- `quantlab_live/mirror.py` logs, per intended fill: our close price, BingX best bid/ask at the
  bar, the price a market order would have paid, and depth at 1× and 2× our size.
- Replace the 0.30% constant with a per-coin cost table (fee + measured half-spread + impact at
  our size). Re-book releases; coins whose cost eats the mean trade (0.4–0.6%) leave the universe.
- Gate: measured cost table in `rnd/exec_costs.json`; book re-run; difference reported.

### Phase 4 — Integrate (≈ 2 days)
- Book levers get their own ledger `rnd/book_trials.jsonl` and their own worker: signals frozen
  to the current release, nested selection, hysteresis (adopt only above the bootstrap band).
- `review.py` weekly: PBO (CSCV) over the book ledger; refuse > 0.5.
- Paper book swaps the book only through this path; signal releases and book releases are
  numbered separately (`release_NNNN` / `book_NNNN`).

## 4. What this does not touch
Signal layer (first audit). RL manager, account stop, market-health halts (closed, decision
log). Shorting (would be a new line). No new hardware.

## 5. Expected outcome
Honest book numbers below today's headline; drawdown lower at equal return from vol targeting
and mean/variance sizing (the only two with strong published evidence); costs that match the
venue. The book stops gaining or losing levers on 0.001 of score.

## References
Moreira & Muir (2017) *Volatility-Managed Portfolios*, JF · Harvey, Hoyle, Korgaonkar, Rattray,
Sargaison, Van Hemert (2018) *The Impact of Volatility Targeting*, JPM · MacLean, Thorp, Ziemba
(2011) *The Kelly Capital Growth Investment Criterion* · López de Prado (2018) *Advances in
Financial Machine Learning* (meta-labelling, bet sizing, CSCV) · Almgren & Chriss (2000) *Optimal
Execution of Portfolio Transactions* · Clenow (2013) *Following the Trend* · in-house:
`HEALTH.md`, `rnd/levers_study.json`, decision log in `README.md`.
