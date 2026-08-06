# Hypothesis

```json
{
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
}
```
