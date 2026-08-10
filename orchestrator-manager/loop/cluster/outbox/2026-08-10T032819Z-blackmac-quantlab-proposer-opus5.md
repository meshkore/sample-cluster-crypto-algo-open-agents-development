## Iteration 25 — proposal

**Module:** DETECTOR

**Claim:** Two disjoint BULL entry rules (H-L015 breakout, H-L020 trend+momentum) both produced the identical frozen 71-trade all-BEAR forward window, proving BULL entries are causally inert while the detector routes 100% BEAR; replacing the tied breadth axis (bull 0.416 ≈ bear 0.413) with the served, signed, mutually-exclusive supertrend regime flag (supertrend_direction > 0 AND close > supertrend) will route at least one 2026 forward bar to a bull regime, moving the forward trade count off the frozen 71 

**Killed by:** Refuted if the in-sample fit score stays at or below the best-known DETECTOR -0.1126 (forward window never opens), OR the forward window opens but the trade count remains 71 with every trade still routed to BEAR. Either outcome shows a supertrend regime axis is no more separable than breadth and the detector is not the binding constraint.

Rotating to BULL as the diagnosis suggested would waste the iteration: the ledger shows BULL entry rules are causally inert (H-L015 and H-L020, two unrelated gates, both froze at 71 BEAR trades / -7.82%). So I explicitly abandon BULL-entry tuning and target the DETECTOR, which is the mechanism suppressing every non-BEAR module. Root cause per H-L021/H-L016: the breadth thresholds are tied (0.416 vs 0.413), so no bar scores bull. Those two prior detector attempts died at the fit gate because they swapped in noisy di/ema composites (H-L016 used close-vs-ema_200 + di dominance; H-L021 used a signed median-breadth axis). This proposal is distinct: it uses supertrend_direction, a served flag that is already +1/-1 signed and mutually exclusive, so the bull and bear regimes cannot collapse onto tied thresholds the way breadth did. The rule is a 7-node, two-comparison mechanism (regime flag positive AND price above the supertrend line for coherence) — small enough to be a mechanism, not an overfit.

- `(supertrend_direction > 0 AND close > supertrend)`