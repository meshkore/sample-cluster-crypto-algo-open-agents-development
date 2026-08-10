## Iteration 58 — proposal

**Module:** DETECTOR

**Claim:** The 2026 window is 100% BEAR because the regime lookback (trend_period=284) exceeds the 212-bar forward window, so the label is decided by pre-lock 2025 data and cannot flip in-window. Seeding the DETECTOR with a within-window trend-state classifier (close above ema_50, ema_21 above ema_50, supertrend up) will cause BULL/SIDEWAYS to be invoked on at least one 2026 bar (currently zero), clear the DETECTOR gate (evolved score > best-known -0.0732), and let the forward return diverge from the froze

**Killed by:** Refuted if, after seeding, >=95% of 2026 bars still classify BEAR (BULL/SIDEWAYS still never invoked) OR the evolved score stays <= -0.0732. Either outcome means the all-BEAR labeling is a genuine reading of the tape, not a lookback-lag artifact, and the DETECTOR direction should be abandoned in favor of a shorter trend_period parameter search only.

H-L058R and H-L057C prove the forward window is a single regime: all 212 bars read 'BEAR', BULL/SIDEWAYS are never invoked, and their forward runs return the incumbent's number exactly (that is what wasted the 16 refuted bull/sideways hypotheses). The target_module POLICY is both out-of-schema and, per the reviewer, unreachable by the search, so the true lever is the DETECTOR. incumbent.trend_period=284 is longer than the ~212-bar 2026 window, which mechanically pins the regime to the 2025 downtrend. The first seed rule is a within-window uptrend classifier built from lookbacks that resolve inside 212 bars (ema_21/ema_50 and the fast-flipping supertrend_direction) so a non-bear label can actually appear; the second peels off low-ADX ranging bars for SIDEWAYS. Both rules are long-only regime classifiers (they gate which module holds, not any short), use only cross-field comparisons (no same-bar tautology), and sit at 10 and 7 nodes.

- `(close > ema_50 AND ema_21 > ema_50 AND supertrend_direction > 0)`
- `(adx < 20 AND close > sma_50)`