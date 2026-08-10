## Iteration 21 — proposal

**Module:** DETECTOR

**Claim:** The detector collapses every 2026 bar to BEAR because its bull/bear axis is a same-bar breadth snapshot whose two thresholds are effectively tied (bull_breadth 0.416 ≈ bear_breadth 0.413), so no bar can ever score as bull; replacing that axis with a signed, mutually-exclusive medium-horizon momentum regime (sign of return_60, confirmed by close vs ichimoku_kijun) will label at least some forward bars bull and move the frozen forward trade count off 71 while lifting the DETECTOR fit above the bes

**Killed by:** Refuted if the fit fails to clear -0.1126 (forward window stays closed), OR the forward window opens but the trade count remains 71 with return still -0.0782 — i.e. the momentum axis reproduces the same all-BEAR routing that breadth did.

The ledger shows two detector axes already dead: H-L016 (instantaneous directional trend — close vs ema_200 plus di_plus/di_minus dominance) and H-L011 (a trend-strength/directional-dominance gate on the bear label). Both are same-bar snapshots and both failed to clear the fit gate. Every non-DETECTOR hypothesis (H-L012..H-L020) was refuted by the same tell — forward stays frozen at 71 trades / -7.82% — because the routing never changes: the detector sends everything to BEAR, so no downstream module can ever be exercised. The root cause named in H-L016 is that breadth does not discriminate (0.416 vs 0.413). The untried axis is medium-horizon momentum persistence: return_60 is inherently signed, so its two branches are mutually exclusive by construction rather than by a fragile threshold gap, and ichimoku_kijun gives a persistence-based (not same-bar-breadth) price confirmation. This is mechanistically distinct from breadth, from DI dominance, and from an ADX/strength gate. If a signed, bimodal axis still routes all forward bars to BEAR, that is strong evidence the 2026 forward window is simply a monotone downtrend and the detector is not the lever — abandon DETECTOR rather than deepen it.

- `(return_60 > 0 AND close > ichimoku_kijun)`
- `(return_60 < 0 AND close < ichimoku_kijun)`