## Iteration 48 — proposal

**Module:** BEAR

**Claim:** BEAR bleeds because it shorts pullback lows inside a rising tape (H-L038's 46 SIGNAL_EXIT losers, -12.55%); replacing the entry with a temporal Donchian downside-breakout gate — close crossing below its 20-day low while trading beneath the 200 EMA — will clear the walk-forward fit gate above the current BEAR best (0.0209) and, if the forward window opens, cut the SIGNAL_EXIT loss channel below -12.55% by structurally excluding continuation-less pullback shorts.

**Killed by:** Refuted if the fit does not clear the gate and lands at or near the degenerate floor (~-0.1008), OR if the forward window opens but SIGNAL_EXIT trade count and loss are not materially reduced versus 46 trades / -12.55%.

The dominant loss is 46 SIGNAL_EXIT shorts (-12.55%) held into recovery — H-L038 diagnosed this as shorting pullback lows in a rising tape. H-L044 shows the recurring failure mode is static AND-chains collapsing to the degenerate floor -0.10078365 (H-L038/039/043 all identical; H-L046's trend-stack -0.34). Every refuted BEAR seed used level comparisons on oscillators (038), exit signals (039), distribution flow (043), or trend flags (046) — none used a temporal cross_down breakout. A fresh 20-day-low breakdown filtered by close<ema_200 is a distinct mechanism: it fires only on genuine downside continuation and is disjoint-by-construction from rising-tape pullback shorts, since a rising tape prints no new 20-day lows below the long-term anchor. Kept to two joined comparisons (7 nodes) to avoid the 3-AND degeneration that floored the prior attempts.

- `(close crosses below low_20 AND close < ema_200)`