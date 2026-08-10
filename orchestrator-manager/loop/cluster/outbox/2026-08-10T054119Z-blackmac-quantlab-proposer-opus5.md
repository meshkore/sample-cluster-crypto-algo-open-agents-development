## Iteration 35 — proposal

**Module:** DETECTOR

**Claim:** The BULL module cannot be served by tuning BULL entries — H-L025 and H-L030 proved any BULL rule yields the same frozen all-BEAR window because the detector never emits a bull state. The one distinguishing fact is that every refuted detector-axis attempt (H-L026 deviation, H-L028 static ema_50/ema_200/close-vs-sma_200, H-L030 static di_plus/di_minus) compared same-bar snapshots that are numerically tied (bull_breadth 0.416 ≈ bear_breadth 0.413) and therefore can never score bull. Replacing that 

**Killed by:** Refuted if the fit fails to clear the detector gate (score ≤ -0.1126), OR if the forward window still routes 100% to BEAR with zero bull-routed bars (trade count stays frozen at 67/71). Either outcome means an event/crossover axis is causally no different from the refuted same-bar snapshots, and detector-based rescue of BULL should itself be abandoned.

The diagnosis rotated the target to BULL, but the ledger is unambiguous that BULL entry tuning is a dead direction: H-L025 and H-L030 both left the window frozen at 71 all-BEAR trades because the detector routes ~100% BEAR, and only a DETECTOR change (H-L031) has ever unfrozen the window (71→67, incumbent -7.82%→-7.11%). So I explicitly abandon BULL-entry tuning and target the only causal lever. What is genuinely new versus the refuted detector attempts is the node type, not the columns: H-L026/H-L028/H-L030 all used gt/lt on same-bar values that the detector itself flags as tied and unable to score bull. A cross_up/cross_down is a state-transition event that is directional and mutually exclusive by construction — bull and bear can no longer share a tied snapshot. The adx>20 gate answers the chop problem that sank H-L033, and pairing the up-cross with a symmetric down-cross gives the detector a distinguishable bull-vs-bear pair for the first time. If even a crossover event axis cannot emit a bull state, that falsifies detector-rescue of BULL entirely and the loop should stop revisiting BULL.

- `(ema_21 crosses above ema_50 AND adx > 20 AND close > ema_200)`
- `(ema_21 crosses below ema_50 AND adx > 20 AND close < ema_200)`