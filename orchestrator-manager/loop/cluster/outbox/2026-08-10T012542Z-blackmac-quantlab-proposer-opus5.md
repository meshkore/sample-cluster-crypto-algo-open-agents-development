## Iteration 16 — proposal

**Module:** DETECTOR

**Claim:** The detector routes all 71 trades to BEAR because bull_breadth (0.416) and bear_breadth (0.413) are near-identical, so the breadth axis does not discriminate regimes; replacing it with a mutually-exclusive directional trend axis (close vs ema_200 confirmed by di_plus/di_minus dominance) will drop the bear-routed trade share below 71 and lift the walk-forward score above the best-known DETECTOR -0.1126.

**Killed by:** Refuted if the bear-routed trade count remains 71 (routing still collapses to one label) OR the walk-forward score stays at or below -0.1126.

H-L006 confirmed the detector only fires as a bear label; the last four iterations left DETECTOR untouched while BULL/BEAR/SIDEWAYS branch edits all failed to open a window. H-L011 already refuted deepening the bear gate with strength+dominance filters (over-conjoined, score -0.167). So I am abandoning the 'add-conditions-to-bear' direction. The novel, untested lever is the discriminator itself: bull_breadth and bear_breadth are effectively equal, so the breadth threshold cannot separate regimes and everything falls through to bear. These two 7-node gates are mechanistically opposite (a bar cannot be both above and below ema_200 with both DI orderings), forcing genuine bull/bear separation instead of a monopolized bear route — the minimal change that attacks the collapse rather than the symptom.

- `(close > ema_200 AND di_plus > di_minus)`
- `(close < ema_200 AND di_minus > di_plus)`