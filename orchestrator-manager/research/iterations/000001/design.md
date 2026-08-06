# Design

Signal is calculated at bar close and filled at the next bar open. This run uses the development partition only.

```json
{
  "assets": [
    "BTCUSDT"
  ],
  "costs": {
    "commission_bps": 10.0,
    "funding_bps_per_bar": 0.0,
    "slippage_bps": 5.0
  },
  "dataset_version": "c2c8feb526b36f9f7e428edc9e236ab05877aaf64f13555b2e979f79d8c5e194",
  "engine_version": "next-open-v1",
  "experiment_id": "EXP-000001-H-MOM-001",
  "hypothesis": {
    "data_required": [
      "OHLCV"
    ],
    "economic_or_behavioral_story": "Slow information diffusion can continue after a range escape.",
    "entry_logic": "target long after trigger; next-open fill",
    "exit_logic": "exit after close below 10-bar mean",
    "expected_failure_modes": [
      "false breakouts",
      "crowded momentum",
      "gap execution"
    ],
    "experiments_needed": [
      "walk-forward",
      "cost stress",
      "lookback perturbation"
    ],
    "family": "volatility_expansion",
    "features": [
      "lagged_close_return",
      "prior_20_bar_high",
      "rolling_range"
    ],
    "id": "H-MOM-001",
    "invalidators": [
      "cost-adjusted edge <= 0",
      "parameter cliff",
      "single-regime dependence"
    ],
    "market_context": "liquid crypto spot",
    "market_mechanism": "A close above the prior range with non-extreme volatility represents information arrival rather than a one-tick breach.",
    "novelty_claim": "Uses an explicit abstention band around unstable volatility.",
    "regime": "all; validate by regime",
    "research_mode": "exploitation",
    "time_horizon": "days to weeks",
    "title": "Persistent return after volatility-normalized breakout",
    "trigger": "close[t] > max(close[t-20:t]) and range volatility is bounded"
  },
  "parameters": {
    "exit_window": 10,
    "lookback": 20,
    "max_vol": 0.04
  },
  "parent_ids": [],
  "test_period": "LOCKED:2025",
  "training_period": "2021-01-01/2023-12-31",
  "validation_period": "LOCKED:2024"
}
```
