## Iteration 30 — proposal

**Module:** DETECTOR

**Claim:** BULL entry tuning is abandoned as causally inert (H-L025 proved any BULL rule yields the same frozen 71-trade all-BEAR forward window at -7.82%); replacing the detector's tied same-bar breadth axis (bull 0.416 ≈ bear 0.413) with a directional-movement axis that is mutually exclusive by construction — +DI vs -DI gated by ADX>20 — will clear the fit gate (walk-forward score > -0.1126, best-known DETECTOR) AND open a 2026 forward window whose trade count differs from the frozen 71 by routing at lea

**Killed by:** Refuted if the fit fails to clear the gate (score ≤ -0.1126) so no forward window opens, OR if the window opens but the 2026 forward trade count stays at 71 with 0 bars classified bull — which would mean the +DI/-DI axis is as one-sided as breadth and the all-BEAR collapse is structural, not axis-specific.

The diagnosis rotates to BULL, but the ledger forecloses BULL deepening: H-L020 and H-L025 show every BULL entry rule collapses to the identical frozen 71-trade all-BEAR window at -7.82%, so BULL is causally inert while the detector routes 100% BEAR — I abandon it explicitly rather than earn a fourth -7.82%. The upstream defect, flagged since H-L021, is the tie: bull_breadth 0.416 ≈ bear_breadth 0.413 are near-equal thresholds on one breadth snapshot, so no bar scores bull. Prior detector fixes (H-L021 median/participation, H-L026 deviation, H-L028 ema/sma trend levels) all tried to REPLACE the axis with a level and failed the gate, H-L028 closest at -0.1147. Untried: a directional-movement (DMI) axis, +DI vs -DI, which is mutually exclusive by construction — the two seed rules cannot both fire, eliminating the tie/dead-zone directly instead of re-tuning around it, and ADX>20 leaves ranging bars neutral. In a rising 2026 tape (per H-L022) +DI>-DI should hold often, producing the bull-classified bars the current detector structurally cannot emit, which is the precise pathology driving the all-BEAR loss.

- `(di_plus > di_minus AND adx > 20)`
- `(di_minus > di_plus AND adx > 20)`