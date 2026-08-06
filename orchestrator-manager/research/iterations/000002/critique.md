# Adversarial critique

```json
{
  "confidence": 0.95,
  "critical_failures": [
    "Result uses synthetic data and has no market-evidence value.",
    "Edge disappears when stated costs are doubled."
  ],
  "possible_repairs": [
    "collect exchange data",
    "simplify rules",
    "expand independent regimes"
  ],
  "required_tests": [
    "point-in-time multi-asset validation",
    "purged walk-forward validation",
    "parameter perturbation",
    "remove best trades",
    "execution delay stress"
  ],
  "suspected_biases": [
    "Performance is not temporally stable across two coarse subperiods."
  ],
  "verdict": "REJECT"
}
```
