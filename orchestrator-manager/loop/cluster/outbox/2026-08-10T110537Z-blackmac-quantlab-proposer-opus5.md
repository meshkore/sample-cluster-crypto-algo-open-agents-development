## Iteration 56 — proposal

**Module:** BULL

**Claim:** A trend-continuation long entry that buys confirmed strength — close above ema_50, a fresh di_plus/di_minus bullish cross, and above-average volume participation — clears the BULL gate (evolved score > best-known 0.0399) and, once the forward window opens, beats the incumbent +1.12%. This inverts the two exhausted BULL frames: the deviation/pullback long that bought weakness (H-L050) and the breadth tie-break that fought the router (H-L036/040/041/045).

**Killed by:** Refuted if the evolved fit scores <= 0.0399 (no gate clearance, no forward window opened), OR it opens a forward window but returns <= +1.12% (no improvement over incumbent). Either outcome means trend-continuation is not the BULL mechanism and the leaf's edge, if any, lies elsewhere.

The diagnosis rotates to BULL after two dead forward windows and four iterations that never touched it, so BULL's leaf is genuinely under-explored while BEAR's -7.11% router sink is already resolved (H-L053, +1.12% incumbent). The ledger shows BULL's two attempted frames are spent: H-L050 bought weakness (deviation: bb_percent_b < 0.2 pullback) and scored -0.0054; H-L036/040/041/045 fought the detector's breadth tie-break and went degenerate. Both are mean-reversion-flavored or routing hacks. The untried, mechanistically opposite hypothesis is to buy strength: enter only when price sits above the medium trend (close > ema_50), directional pressure freshly turns up (di_plus crosses above di_minus — the 'trend' rule family), and participation confirms the move (volume > 1.3x its 20-bar average — the 'participation' family). The entry seed is 12 nodes, the exit seed (directional cross-down or close losing ema_21) is 7 — both well under 24, each three-or-fewer joined comparisons, no field compared to itself. This is a distinct falsifiable mechanism, not a repeat of any ledger entry.

- `(close > ema_50 AND di_plus crosses above di_minus AND volume > volume_sma_20*1.3)`
- `(di_plus crosses below di_minus OR close < ema_21)`