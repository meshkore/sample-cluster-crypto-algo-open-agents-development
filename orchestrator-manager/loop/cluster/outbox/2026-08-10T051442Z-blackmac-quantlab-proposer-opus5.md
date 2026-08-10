## Iteration 33 — proposal

**Module:** BEAR

**Claim:** Gating BEAR entries on a chop-filtered directional downtrend (adx > 25 AND di_minus > di_plus AND supertrend bearish) will clear the walk-forward fit gate (score > 0.0209, the best-known BEAR score) and, on the forward window, cut SIGNAL_EXIT trades below 46 while raising win rate above 27% — because the 46 near-breakeven losers (-0.27% avg) are shorts fired in choppy/rising tape that an ADX trend-strength filter rejects.

**Killed by:** The fit fails to clear the gate (score <= 0.0209), OR the forward window opens with SIGNAL_EXIT count still ~46 and win rate still ~27% — showing the ADX chop filter is causally inert, like the EMA-structure gate in H-L032.

H-L032 already refuted entry gating via EMA structure (close<ema_200, 50/200 cross), so I am NOT repeating moving-average position. The distinct, untried lever is a trend-QUALITY filter: adx>25 requires a genuine trending regime and rejects the choppy/rising pullbacks where the 46 SIGNAL_EXIT losers (-0.27% avg, 27% win) originate — something EMA position cannot do. di_minus>di_plus adds directional dominance and supertrend_direction<0 confirms an established downtrend, both from the 'trend' rule family but never combined with an ADX chop gate on BEAR. Three joined comparisons (10 nodes), a mechanism not a fit. If this too fails the gate, the evidence says BEAR entry-regime gating as a whole should be abandoned and the loop should return to the detector routing that produced the only confirmed move (H-L031).

- `(adx > 25 AND di_minus > di_plus AND supertrend_direction < 0)`