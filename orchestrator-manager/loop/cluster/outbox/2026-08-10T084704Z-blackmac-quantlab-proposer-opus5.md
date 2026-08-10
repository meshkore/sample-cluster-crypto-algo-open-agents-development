## Iteration 48 — proposal

**Module:** BEAR

**Claim:** Reseeding BEAR as a momentum-continuation short — enter only on a confirmed downside breakout (close crossing down through the 55-bar low) with trend strength present (adx > 25), and exit promptly when price reclaims the 21 EMA — will shrink the SIGNAL_EXIT loss channel below its current -12.55% and lift the walk-forward fit off the degenerate -0.1007 floor toward the 0.0209 best-known, because the 46 losing shorts were pullback/rollover shorts into a rising tape rather than breakdown shorts.

**Killed by:** Refuted if the walk-forward fit stays at or below the -0.1007 degenerate floor (breakout bars too sparse to be a mechanism), OR the forward SIGNAL_EXIT channel fails to improve on -12.55% and total forward return does not beat -7.11%. Either outcome means shorting is not salvageable by relocating entries to breakouts, and BEAR entry tuning should be abandoned in favor of detector-level suppression of the all-BEAR routing freeze.

The diagnosis localizes the bleed to 46 SIGNAL_EXIT shorts (-12.55%) held while the tape recovers, not to too few downtrends. Every prior entry fix in the ledger shorted the wrong location or over-constrained: H-L038 shorted oscillator rollovers near highs, H-L043 a triple-AND distribution gate, H-L046 a triple-AND supertrend/di/adx trend-flag — all three collapsed to the same -0.1007 floor, exactly the over-constraint H-L044 itself named. This hypothesis is disjoint by construction: it is a trend-following short that fires only on a genuine 55-bar downside breakout (cross_down close/low_55) filtered by a single trend-strength term (adx>25), so it shorts new lows rather than pullback lows in a rising 2022-2026 tape. It uses only two joined comparisons for entry — deliberately below the triple-AND regime that keeps degenerating — plus a fast reclaim exit (cross_up close/ema_21) that directly attacks the held-too-long SIGNAL_EXIT losers. This entry axis and this entry+exit pairing do not appear anywhere in the ledger tail (H-L038 through H-L047).

- `(close crosses below low_55 AND adx > 25)`
- `close crosses above ema_21`