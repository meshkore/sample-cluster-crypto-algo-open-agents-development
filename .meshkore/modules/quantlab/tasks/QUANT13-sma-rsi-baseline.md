---
id: QUANT13
title: "Build the simplest complete strategy as a tunable baseline, and fix the forward-phase timeframe bug"
status: in_progress
priority: critical
owner: unassigned
category: quantlab
initiative: liquid-ml-research
created: 2026-08-04
updated: 2026-08-04
tags: [hypothesis, baseline, money-management, parameter-search, bug]
depends_on: [QUANT11, QUANT12]
blocks: []
---

## Why this exists

Two separate things came out of the same operator message, and they belong
together because the second one invalidates how the first would have been
measured.

**1. Nine families, no baseline.** Every family tested here so far
(volatility_expansion, volume_climax, trade_abstention, trend_persistence,
supertrend_adx, donchian_breakout, multi_factor_trend, regime_switching) was
measured against buy-and-hold and against an equal-weight basket, but never
against a *floor* — the simplest rule that could possibly work. Without that
floor, "+36.97% Phase-1" from a three-factor vote has no interpretation:
there is no way to tell whether the three factors earned anything or whether
two moving averages would have done the same. The operator's point was exact:
a system with two moving averages and an RSI should demonstrably fire hundreds
of trades on real candles, and if this lab cannot show that, the problem was
never the strategy.

**2. A real bug: the forward phase ignored `FAMILY_DATA_OVERRIDES`.** QUANT9
introduced per-family data overrides so a family could be swept on its own
timeframe and symbol list instead of the shared daily/386-asset universe.
`historical.py` honored the override; `forward.py` did not — it read
`asset_universe` unconditionally. Any override family would therefore have
been swept on 15-minute candles over three majors and then forward-tested on
daily candles over 386 unrelated assets, with the second result presented as
the first strategy's out-of-sample evidence. It had not bitten yet only
because no override family had reached the forward queue.

## What was built

### `H-SMARSI-001`, family `sma_rsi_trend`

Hourly candles, five deepest USDT majors (BTC, ETH, BNB, SOL, XRP).

- **Three conditions, all required to enter**: fast SMA above slow SMA (trend
  state); RSI inside a band, above a floor and *at or below* a ceiling
  (momentum confirms but is not exhausted); close above the fast SMA (price
  confirms, not the averages alone).
- **Two exits, either sufficient**: fast SMA falls back below slow SMA, or
  RSI exceeds the ceiling. Entry and exit are asymmetric on purpose — the
  position survives losing the price confirmation, so an ordinary pullback
  inside a live trend does not churn it.
- **Binary confidence, 1.0.** This is a design decision, not a shortcut. A
  graded signal is compared against the money-management layer's
  `minimum_confidence` threshold, so a policy demanding 0.75 silently vetoes
  a 2-of-3 vote at 0.667 — the strategy then looks inert when it is being
  blocked. Emitting 1.0 puts *every* sizing decision in money management
  (volatility target, risk per trade, position cap, stop/target brackets,
  volume participation, drawdown deleverage) and makes this family's trade
  count a measurement of the signal alone.
- **Hourly, not daily or 15-minute.** Daily caps a seven-month forward window
  at ~215 bars per asset, which makes trade count a property of the
  resolution rather than of the strategy. 15-minute quadruples cost drag
  against a signal this plain. Hourly gives ~5,100 forward bars per asset.

The RSI band is load-bearing and was found by a failing test: checking only
the floor made the ceiling exit self-defeating — a strong trend pins RSI above
the ceiling, so the position closed and the next bar re-opened it, paying
costs on every bar for no change in exposure. `test_an_rsi_ceiling_breach_
closes_the_position` fails if that regresses.

### `FocusedDataset` (`data.py`), replacing the private loader in `historical.py`

One loader now owns override-family market data, used by **both** phases, which
is what structurally prevents them from diverging again. It keeps the
research/forward split intact — pre-2026 bars go through `DataManager`, which
refuses 2026 data outright, and 2026 bars through `ForwardDataManager` — and
caches under the same `processed/<provider>/<symbol>/<interval>/` layout the
daily universe already uses. Cache freshness is read from the manifest's
`observed_end`, because `save_csv` names files by content hash and the
directory listing carries no chronology; the previous `sorted(glob)[-1]` picked
a cache by hash, not by recency.

## Parameter search

99-point grid over fast/slow SMA and the RSI band, on **pre-2026 BTCUSDT
only**, driven through the production strategy class, cost model and portfolio
engine — the sweep is not a second simulator. The winner is then checked on
the four untouched majors as its own held-out evidence, and still has to clear
walk-forward and the forward window like anything else.

Genetic/CMA-ES search was considered and deliberately not used for a
five-parameter space: any search powerful enough to find a good corner of a
grid this small is powerful enough to find a fictional one, and a coarse grid
plus held-out assets is the more defensible discipline. This is recorded as a
decision, not an omission — it should be revisited if the parameter count
grows.

## Where this explicitly does NOT overreach

An SMA cross with an RSI filter is textbook material and almost certainly
already arbitraged. The novelty claim is zero and says so. This is built as a
measurable floor and as a search target, and the honest prior is that it has
no surviving edge. If it does not, that is still the first useful thing this
lab will have established about its other eight families.

## Acceptance criteria

- No exemption from the drawdown limit, cost model, benchmark comparison, or
  the 2026 lock.
- The Phase-1 winner is reported with the full grid, not only its best point —
  a result that exists at one narrow corner is reported as a fitted artifact.
- Compared head-to-head against H-MULTI-001 (QUANT11) on trade count as well
  as return, since trade count was the operator's specific objection.
- The forward-phase override fix is covered by a test that fails if
  `forward.py` goes back to reading `asset_universe` for an override family.
- Reported honestly regardless of outcome.

## Stage-1 result: the signal grid says nothing, and that is the finding

All **99 of 99** signal parameter sets on pre-2026 BTCUSDT hourly came back
negative under the lab's default portfolio policy. Best point: fast 20 / slow
100 / RSI band 45-90, **-11.07% return, 22.32% max drawdown, 742 trades**.
Worst: -24.2%. Every drawdown in the grid landed between **22.3% and 24.0%**.

A 99-point grid over four parameters does not produce a drawdown range 1.7
points wide unless the binding constraint is somewhere other than the signal.
That uniformity is a property of the portfolio policy, and chasing signal
parameters under it would have been measuring nothing — which is the reason
stage 1 is reported as a negative result about the *method* rather than as
"H-SMARSI-001 has no edge".

One weak signal-level regularity did survive: `rsi_ceiling=90` occupies nine
of the top ten rows, and the tighter ceilings (70, 80) are uniformly worse.
Exiting a strong trend because it is strong costs more than it saves. That is
consistent with the hypothesis's own recorded `expected_failure_modes`.

## Stage-2 finding: the policy was calibrated for the wrong bar size

Identical signal, identical candles, identical costs — only the portfolio
policy differs:

| policy | return | max DD | trades |
|---|---|---|---|
| lab default (5% stop, 10% target, deleverage ramp from 10% DD) | **-11.92%** | 22.69% | 739 |
| same, deleverage ramp disabled | **-7.23%** | 24.37% | 739 |
| 20% stop, 95% target, ramp disabled | **+17.99%** | **10.92%** | 489 |

The deleverage-ramp row is a **clean** comparison: position sizing is
identical, only the ramp changes, and it is worth **+4.7 points**. The ramp
scales size by `(0.25 - current_dd) / (0.25 - 0.10)`, so at 22% drawdown the
lab trades at 20% of normal size — exactly when recovering requires normal
size. It is our own choice below the mandated 25% abort, and it prevented
nothing measurable here.

The third row is **not** a clean comparison, and saying so matters more than
the number. `stop_loss_pct` does double duty in the engine: it is the exit
trigger (`portfolio.py:280`) *and* the denominator of the sizing formula
(`portfolio.py:339`, `risk_budget / stop_loss_pct`). Widening 5% -> 20%
therefore cuts notional roughly in half at the same time as it moves the exit,
so that row conflates "stopped harvesting noise" with "took half the risk" and
cannot be attributed to either. `diag_decompose.py` separates them by varying
one dial at a time and reporting realized average exposure alongside.

**Two consequences beyond this task:**

1. `maximum_position_fraction=0.2` means a *single-asset* backtest is
   structurally capped at 20% of capital invested, and a three-asset one at
   60%. Earlier focused-scope results were being compared against
   buy-and-hold as if fully invested when they were not — S00826
   (supertrend_adx, 15m, three majors, -14.12%) is affected and cannot be
   called a signal failure until it is rerun with a policy whose cap times
   asset count reaches 100%.
2. The engine cannot express "wide stop, full size", because one parameter
   controls both. Splitting `stop_loss_pct` into a sizing distance and an exit
   distance is the obvious fix and is deliberately **not** done inside this
   task — it changes every stored policy in the database and belongs in its
   own change with its own tests.

## Decomposition: which dial did the work, at matched exposure

The stage-2 table could not attribute its own result, because `stop_loss_pct`
moves the exit and the position size together. `diag_decompose.py` varies one
dial at a time from the default and reports realized average exposure
(`1 - cash/equity`) so the size effect is measured rather than assumed.
Signal held fixed at fast 20 / slow 100 / RSI 45-90, BTCUSDT hourly, 73,284
bars.

| scenario | return | max DD | trades | avg exposure | time in market |
|---|---|---|---|---|---|
| A  default: 5% stop, 10% target, ramp on | -11.07% | 22.32% | 742 | 8.1% | 46.2% |
| B  A + deleverage ramp off | -6.88% | 23.45% | 742 | 8.9% | 46.2% |
| C  B + take-profit 95%, stop still 5% | -22.64% | 25.05% | 348 | 7.8% | **ABORTED** |
| D  C + stop 20% | **+18.00%** | **10.38%** | 492 | **4.8%** | 46.4% |
| E  D with position cap raised to 0.80 | +18.00% | 10.38% | 492 | 4.8% | 46.4% |
| F  C with cap 0.10, cut to match D's exposure | -8.66% | 14.65% | 600 | **4.8%** | 46.3% |

**D versus F is the clean isolation**: identical average exposure (4.8%),
identical signal, identical costs, differing only in stop distance. The wide
stop is worth **+26.7 points**. The noise-harvesting explanation survives the
control; the size effect was not doing the work.

Four further findings, each of which applies to every family in the lab and
not only to this one:

1. **The two exit dials are not independent.** Scenario C — wide take-profit
   with a tight stop — is the only row that tripped the mandated 25% abort. It
   holds losers to -5% while never banking the +10% winners. Removing the
   take-profit is only safe once the stop is wide.
2. **`maximum_position_fraction` is not binding.** E is bit-identical to D with
   the cap raised fourfold. What binds is `risk_budget / stop_loss_pct`. Every
   previous discussion of the position cap as a constraint was aimed at the
   wrong parameter.
3. **The lab trades at 4.8-8.9% average exposure and is in the market 46% of
   the time**, i.e. roughly 10-17% of capital deployed when deployed at all.
   With `risk_per_trade = 0.02` divided by the stop distance, positions come
   out microscopic. This caps absolute return for *any* signal, however good,
   and is the most plausible single explanation for eight months of small
   numbers across nine families.
4. **The drawdown budget is 25% and the best configuration uses 10.4 of it.**
   Fifteen points of mandated risk budget sit unused. No signal tuning recovers
   them; only sizing does. Stage 4 states that as the actual optimisation —
   maximise return subject to `max_drawdown < 0.25` — with the abort left
   untouchable and any row that trips it disqualified rather than excused.
