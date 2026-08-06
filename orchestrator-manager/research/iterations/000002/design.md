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
  "experiment_id": "EXP-000002-H-REV-001",
  "hypothesis": {
    "data_required": [
      "OHLCV",
      "taker volume"
    ],
    "economic_or_behavioral_story": "Urgent one-sided flow can exhaust short-term liquidity and mean-revert.",
    "entry_logic": "target long after climax close",
    "exit_logic": "time stop or recovery to trailing mean",
    "expected_failure_modes": [
      "catching falling knives",
      "regime shift",
      "bad open fill"
    ],
    "experiments_needed": [
      "crash-regime split",
      "execution delay",
      "remove best trades"
    ],
    "family": "volume_climax",
    "features": [
      "lagged_return",
      "relative_volume",
      "taker_imbalance"
    ],
    "id": "H-REV-001",
    "invalidators": [
      "continued information-driven selloff",
      "insufficient trades",
      "volume leakage"
    ],
    "market_context": "liquid crypto spot",
    "market_mechanism": "A large negative return on exceptional lagged volume is followed by stabilization when forced sellers are exhausted.",
    "novelty_claim": "Requires exhaustion magnitude and a deterministic short holding period.",
    "regime": "all; validate by regime",
    "research_mode": "causal_exploration",
    "time_horizon": "one to five bars",
    "title": "Volume-climax exhaustion reversal",
    "trigger": "return[t] is unusually negative and volume[t] exceeds trailing baseline"
  },
  "parameters": {
    "holding": 3,
    "return_threshold": -0.025,
    "volume_multiple": 1.5,
    "volume_window": 20
  },
  "parent_ids": [],
  "test_period": "LOCKED:2025",
  "training_period": "2021-01-01/2023-12-31",
  "validation_period": "LOCKED:2024"
}
```
