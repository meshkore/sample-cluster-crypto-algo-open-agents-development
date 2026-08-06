# Hypothesis

```json
{
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
}
```
