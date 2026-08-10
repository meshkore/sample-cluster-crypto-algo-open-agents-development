## Iteration 6 — proposal

**Module:** DETECTOR

**Claim:** The DETECTOR is gating to zero trades because its regime condition is an over-conjoined AND that never fires; replacing it with a minimal two-condition trend+participation bear gate will produce a nonzero 2026 forward trade count AND lift the walk-forward fit above the incumbent best of 0.0209.

**Killed by:** Refuted if either loosened gate still opens zero trades in the forward window, OR the walk-forward fit stays below 0.0209. Either outcome means the barrier is not gate tightness but something downstream — the BEAR module standing aside even under a bear label, or the scorer itself — and the DETECTOR should stop being the target.

The diagnosis says the run was gated, not outvoted, and H-016 already established the BEAR entries are sound — so the fault is the gate refusing to name a bear regime, not the rule behind it. H-L002–H-L005 are four identical 'evolve the detector's entry/exit rules' hypotheses, all refuted the same way (score never reaching 0.0209, forward window never opened) and plateauing near −0.11. That repetition is evidence the entry/exit framing is exhausted and should be abandoned, not iterated a fifth time. I reframe the DETECTOR as what it is — a regime gate — and test the specific mechanism 'the gate is too tight.' Both seeds are two joined comparisons (7 nodes each, well under the cap) drawn from distinct rule families: seed 1 is pure trend (price under the 200 EMA with di_minus dominating di_plus); seed 2 pairs trend (supertrend_direction below zero) with participation (volume above its 50-day mean), matching the deviation/participation/trend taxonomy. Deliberately loose so the gate can actually fire; the kill condition falsifies cleanly if a firing gate still yields zero trades or fails to clear 0.0209.

- `(close < ema_200 AND di_plus < di_minus)`
- `(supertrend_direction < 0 AND volume > volume_sma_50)`