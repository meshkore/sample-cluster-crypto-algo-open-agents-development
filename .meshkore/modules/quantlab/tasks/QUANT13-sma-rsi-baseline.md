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
