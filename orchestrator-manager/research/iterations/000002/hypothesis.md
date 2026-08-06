# Hypothesis

```json
{
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
}
```
