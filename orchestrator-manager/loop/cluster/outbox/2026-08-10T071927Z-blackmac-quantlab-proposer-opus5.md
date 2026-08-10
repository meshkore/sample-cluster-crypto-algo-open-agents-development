## Iteration 42 — proposal

**Module:** SIDEWAYS

**Claim:** The SIDEWAYS module has only ever been fed volatility-compression (bb_width, H-L034) and entry-signal tuning (H-L019/024/029/037), which either froze the window or could not displace BEAR on shared bars; giving it a trend-strength-ABSENCE activation gate (adx < 20 with price oscillating inside the Bollinger band, bb_percent_b in [0.2,0.8]) will route a nonzero fraction of the 67 bars to SIDEWAYS, break the 67/67 all-BEAR freeze, and open a forward window whose return departs from the frozen incu

**Killed by:** The forward window again reports ~67 trades all routed to BEAR with return unchanged at -7.11% (SIDEWAYS trade count 0), showing that a module activation rule cannot override BEAR's routing priority and that only a detector-priority change can free the state.

The diagnosis rotates to SIDEWAYS, but the ledger shows every prior SIDEWAYS attempt froze the window (H-L034/037) because the detector routes 67/67 to BEAR. The distinguishing, never-tried axis is trend-strength absence rather than volatility compression (H-L034) or price-vs-mean deviation (H-L026): adx < 20 defines a non-trending tape where BEAR's directional condition cannot fire, so bb_percent_b-in-band containment (seed 1) or Aroon-oscillator parity (seed 2) can claim those bars disjoint-by-construction from BEAR. This is the first SIDEWAYS seed whose success is measured by a change in routing, not by entry-signal quality; if it too freezes at -7.11%, the kill condition proves the lever lives in detector priority, not module rules.

- `(adx < 20 AND bb_percent_b > 0.2 AND bb_percent_b < 0.8)`
- `(adx < 20 AND aroon_osc < 25 AND aroon_osc > -25)`