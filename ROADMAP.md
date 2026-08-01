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
