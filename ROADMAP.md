# Roadmap

## Phase 0 — audited vertical (implemented)

- Persistent 12-state research loop and resume support.
- SQLite experiment memory, exact hashes and similarity search.
- Deterministic synthetic data plus Binance public OHLCV adapter.
- Next-bar backtest with commission, slippage and funding hooks.
- Three mechanism-led hypothesis families, adversarial critique and reports.
- Golden accounting, temporal-integrity, persistence and deduplication tests.

## Phase 1 — trustworthy market data

- **Implemented:** continuously refreshed active Binance Spot/USDT universe and
  progressive historical/forward downloads with coverage telemetry.
- Add Polars/Parquet partitions and DuckDB catalog with checksums and lineage.
- Add Binance futures funding, mark price, open interest, trades and liquidations.
- Record listings/delistings and build point-in-time universes.
- Reconcile samples against exchange statements and independent calculations.
- **Implemented foundation:** content-addressed CSV artifacts, complete-field
  dataset hashes, checksum/lineage manifests, and fixed-interval missing-data,
  clock-alignment and requested-boundary audits.
- Add corporate/instrument change and liquidity audits; migrate the audited
  artifact contract to Polars/Parquet partitions and a DuckDB catalog.

## Phase 2 — statistical validation

- **Implemented and wired in (2026-08-03):** rolling walk-forward folds with
  an embargo, median-of-folds selection with a consistency floor, and a
  Spearman instrument that measures either selection protocol against
  forward rank (`quantlab walkforward`). `HistoricalUniverseEvaluator` now
  runs `WalkForwardEvaluator` and calls `walkforward.record()` for every
  Phase-1 candidate that clears criterion 10 (`status=='COMPLETE'` and
  `return_pct>0`), reusing the bars and policy the Phase-1 backtest already
  built rather than reloading anything. `optimization.py` then prefers that
  fold evidence over the in-sample query once it exists for a family.
  Gating on Phase-1 profitability was the answer to the open cost question:
  most candidates fail that bar (249 of 603 historically), so folding only
  the survivors keeps the per-candidate cost multiplier from applying to
  every seed and mutation. A candidate that never opened a position
  (`return_pct==0.0`) is skipped rather than folded, since a strategy that
  never traded has nothing for the fold split to measure either way.
  **Next:** whether 2 years of training and 6 months of testing is the right
  shape — charter open question 1 — and whether `walkforward_rank_correlation`
  actually improves on the +0.06 in-sample baseline once enough Phase-1
  survivors have both fold evidence and a completed 2026 forward run to be
  compared against. `quantlab walkforward` reports both numbers together and
  will keep returning null for the walk-forward side until that population
  exists.
- Purged and combinatorial purged cross-validation with embargo.
- Probabilistic/Deflated Sharpe, stationary bootstrap and multiple-testing ledger.
- Parameter surfaces, cost/execution delays, asset/regime transfer and trade-order
  Monte Carlo.
- Locked generation protocol for the 2025 holdout.

## Phase 3 — portfolio research

- **Implemented long-only baseline:** USD 100,000 portfolio, USD 1,000 minimum
  sleeves, risk/stop-derived sizing, stop loss, take profit and detailed trade ledger.
- Add partial exits, trailing stops, liquidity capacity and confidence calibration.
- Volatility targeting, constrained fractional Kelly, correlation budgets,
  drawdown controls and kill switches.
- MAP-Elites cells and an explicit multi-objective Pareto archive.

## Phase 4 — ML, only after data/backtester sign-off

- Reproducible feature registry and purged model pipelines.
- Baselines: regularized logistic regression, boosting, HMM/change points.
- Separate regime, event, direction, trade-gate, execution and risk models.
- Calibrated abstention; small temporal networks only after beating baselines.

## Phase 5 — scaled autonomous research

- Sandboxed strategy implementation workers and compute/storage budgets.
- Source-aware internet research with citation deduplication.
- Diversity quotas, family cooling, lineage-aware mutation and ablations.
- PostgreSQL/object storage and distributed, deterministic workers.
