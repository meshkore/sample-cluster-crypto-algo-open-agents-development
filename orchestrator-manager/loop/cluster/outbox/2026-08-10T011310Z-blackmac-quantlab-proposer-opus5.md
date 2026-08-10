## Iteration 15 — proposal

**Module:** BULL

**Claim:** Replacing the BULL entry with a distinct 55-day-high breakout gate confirmed by trend strength (adx > 25) and positive money flow will change the 2026 forward trade count away from the frozen 71 and lift forward return above the incumbent -0.0782.

**Killed by:** The forward run again returns ~71 trades at ~-7.82% (statistically indistinguishable from the incumbent), which refutes the idea that BULL rules are the lever and proves the BULL branch is unrouted dead code — meaning effort must move to the DETECTOR's regime labeling, not BULL.

The incumbent's -7.82% on 71 trades at a 27% win rate is an entirely bear-routed loss (H-L006 confirmed the DETECTOR emits only bear labels). H-L010 already tried a BULL long gate (close>ema_200, di_plus>di_minus) and came back with an IDENTICAL forward run — -7.82% on 71 trades — which is the tell that the BULL branch never fires because the DETECTOR does not route to it. I am deliberately NOT repeating H-L010's EMA/DI trend-follow gate; this is an orthogonal breakout+strength+flow entry. The value of this hypothesis is that its kill condition is diagnostic: if BULL is genuinely live, a completely different entry mechanism must move the trade count off 71; if the run comes back identical again, we have falsified the whole premise that BULL rules are tunable in the current stack and should abandon BULL to fix DETECTOR regime routing, rather than deepen it.

- `(close crosses above high_55 AND adx > 25 AND chaikin_money_flow > 0)`
- `(close crosses below ema_21 OR chaikin_money_flow < 0)`