## Iteration 51 — proposal

**Module:** DETECTOR

**Claim:** The -7.11% floor is an arbitration defect that lives in the DETECTOR, not in any leaf module: with bull_breadth (0.423) sitting just above bear_breadth (0.392) the bands nearly touch, BEAR wins every shared bar, and 67/67 trades route short into a rising tape (H-L045). Installing detector-level precedence — BEAR is admitted ONLY under a structurally confirmed downtrend (close < ema_200 AND di_minus > di_plus AND ema_50 < ema_200), and a weak-trend / mid-band chop state (adx < 20 with bb_percent_

**Killed by:** Refuted if the fit fails to clear the gate above -0.0732 (no forward window opens), OR the window opens but routing remains >=90% short, OR forward return does not beat the incumbent -7.11%.

The last four leaf-module attempts (H-L047/048/049/050) never opened a window, and the three prior arbitration fixes (H-L042 sideways-absence gate, H-L045 mutually-exclusive tie-break, H-L046 bear trend flag) all failed because they tried to force displacement from INSIDE the leaf modules, which structurally cannot override the detector's breadth arbitration on shared bars. The defect belongs to the DETECTOR, so I place the fix there. Two seeds, each 2-3 joined comparisons: (1) a chop/no-trend precedence rule (adx<20 with price mid-band) that diverts bars to SIDEWAYS before BEAR can claim them — the mean-reversion path the ledger has barely explored; (2) a BEAR admission gate that requires a genuine established downtrend (below the long MA, negative directional movement, and ema_50<ema_200). This is deliberately distinct from H-L046's refuted adx>25/supertrend triple: no adx term, no supertrend, and it demands MA-structure downtrend, which is exactly the condition that shorts-into-a-rising-market fail — the pattern behind the STOP_LOSS tail flagged in H-L049. If the market that produced -7.11% was net rising, most of those 67 short bars should now fail seed (2) and fall to the chop/SIDEWAYS branch.

- `(adx < 20 AND bb_percent_b < 0.8 AND bb_percent_b > 0.2)`
- `(close < ema_200 AND di_minus > di_plus AND ema_50 < ema_200)`