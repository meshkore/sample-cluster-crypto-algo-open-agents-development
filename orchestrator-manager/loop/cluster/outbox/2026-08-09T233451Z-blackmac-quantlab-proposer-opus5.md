## Iteration 8 — proposal

**Module:** BEAR

**Claim:** BEAR's -7.82% is whipsaw: it shorts non-trending chop and bear-rally bounces, so 48 SIGNAL_EXIT trades bleed -12.53% at a 27% win rate. Gating entries on genuine downtrend strength (ADX>25) AND directional dominance (di_minus>di_plus) on top of a long-term-downtrend context (close<ema_200) will raise the 2026 forward win rate above 27% and cut the SIGNAL_EXIT loss below -12.53%, while still taking at least ~15 forward trades.

**Killed by:** Refuted if the forward run takes fewer than ~10 trades (the filter is merely starving the module, not improving it), OR win rate stays at or below 27%, OR aggregate forward return is no better than the incumbent -7.82%.

The diagnosis isolates the loss to SIGNAL_EXIT (48/71 trades, -12.53%) with a 27% win rate. SIGNAL_EXIT-dominated loss plus a sub-30% win rate is the whipsaw signature: shorts placed in non-trending regimes get flipped out on the bounce. H-L006 confirmed the gate can fire but proved it fires indiscriminately into chop. H-L007 shows a broad genetic search over BEAR rules does not clear the gate, so the lever is not another search but a minimal mechanistic filter that separates real downtrends from chop: ADX supplies trend STRENGTH (kills low-ADX whipsaw), di_minus>di_plus supplies DIRECTION (down actually dominant), and close<ema_200 supplies long-term CONTEXT. Three joined comparisons, 10 nodes — a mechanism, not a fold-fit. This deepens the confirmed H-L006 direction rather than repeating the refuted H-L007 one.

- `(adx > 25 AND di_minus > di_plus AND close < ema_200)`