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
  "experiment_id": "EXP-000003-H-ABS-001",
  "hypothesis": {
    "data_required": [
      "OHLCV"
    ],
    "economic_or_behavioral_story": "Trend signals lose value in noise-dominated or panic regimes.",
    "entry_logic": "long only when trend and authorization gate agree",
    "exit_logic": "flat when either condition fails",
    "expected_failure_modes": [
      "volatility clustering",
      "late exits",
      "reduced sample"
    ],
    "experiments_needed": [
      "gate ablation",
      "volatility-band perturbation",
      "regime transfer"
    ],
    "family": "trade_abstention",
    "features": [
      "fast_slow_mean_gap",
      "realized_volatility"
    ],
    "id": "H-ABS-001",
    "invalidators": [
      "gate only curve-fits exposure",
      "turnover offsets benefit",
      "narrow thresholds"
    ],
    "market_context": "liquid crypto spot",
    "market_mechanism": "Intermediate realized volatility permits price discovery while extremes represent stasis or disorder.",
    "novelty_claim": "Treats abstention as a separate authorization rule.",
    "regime": "all; validate by regime",
    "research_mode": "exploitation",
    "time_horizon": "days",
    "title": "Volatility gate for trend abstention",
    "trigger": "fast mean exceeds slow mean only inside volatility band"
  },
  "parameters": {
    "fast": 8,
    "max_vol": 0.03,
    "min_vol": 0.004,
    "slow": 30,
    "vol_window": 15
  },
  "parent_ids": [],
  "test_period": "LOCKED:2025",
  "training_period": "2021-01-01/2023-12-31",
  "validation_period": "LOCKED:2024"
}
```
