## Iteration 38 — proposal

**Module:** BEAR

**Claim:** The BEAR bleed comes from shorting pullback LOWS inside a rising tape (H-L032's 46 SIGNAL_EXIT losers, -12.55%), not from too few confirmed downtrends. Entering shorts only from a position of upside extension that is just beginning to roll over — RSI still elevated, Williams %R in its upper half, close crossing back below the 21 EMA — will clear the BEAR fit gate (score > 0.0209) and, on the forward window, cut SIGNAL_EXIT losers below 46 and lift forward return above the incumbent -7.11%.

**Killed by:** Refuted if the fit score does not exceed 0.0209 (window stays closed, as in H-L032/H-L033), OR if the window opens but SIGNAL_EXIT loser count is not reduced below 46 and forward return does not beat -7.11%.

Every prior BEAR attempt (H-L032 downtrend-structure gate; H-L033 ADX>25 + di_minus>di_plus + supertrend-bearish) added conjunctive strong-downtrend CONFIRMATION and both died at the fit gate (-0.10 << 0.0209): stacking trend filters starves the trade count and tanks the in-sample score. This proposes the orthogonal axis never tried on BEAR — a deviation/exhaustion entry, not a trend-confirmation gate. The diagnosis is explicit that losers are 'shorts opened during pullbacks': a pullback low has LOW RSI, so gating on rsi_14 > 55 and williams_r > -50 structurally forbids exactly those entries, while cross_down(close, ema_21) is the single rollover trigger — 10 nodes, three joined comparisons, a mechanism not an overfit. It is deliberately NOT another ADX/DI/supertrend stack, which the ledger has already killed twice.

- `(rsi_14 > 55 AND williams_r > -50 AND close crosses below ema_21)`