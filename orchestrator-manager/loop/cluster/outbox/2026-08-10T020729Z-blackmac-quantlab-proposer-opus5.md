## Iteration 19 — proposal

**Module:** SIDEWAYS

**Claim:** A range-regime SIDEWAYS entry gated on weak two-sided Aroon trend (aroon_up<70 AND aroon_down<70) with a stochastic cross up out of oversold will move the 2026 forward trade count off the frozen 71 by routing some range-bound bars to mean-reversion longs instead of BEAR shorts.

**Killed by:** Forward trade count stays exactly 71 and forward return stays -7.82%. That refutes reachability: the SIDEWAYS module is dead code under the current detector, and tuning its entry rules (H-L009, H-L014, and this) is a dead direction to be abandoned in favor of the detector's collapsed breadth axis.

H-L009 and H-L014 both returned the identical frozen forward (-7.82% on 71 trades), the signature of a module that never fires. H-L016 confirms the detector routes all 71 trades to BEAR because bull_breadth (0.416) and bear_breadth (0.413) are near-identical, leaving no gap for a sideways label. This makes SIDEWAYS-entry tuning inert. Rather than a fourth cosmetic edit, this is a falsification probe: a range entry distinct from H-L009 (weak Aroon on both sides + stoch cross out of oversold, no adx, no bb_lower cross). If it moves the count, SIDEWAYS is live and worth developing; if it freezes at 71/-7.82% again, the evidence says abandon SIDEWAYS and attack the detector's collapsed breadth axis instead.

- `(aroon_up < 70 AND aroon_down < 70 AND stoch_k crosses above 20)`