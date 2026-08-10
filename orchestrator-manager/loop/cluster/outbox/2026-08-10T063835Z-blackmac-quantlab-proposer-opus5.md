## Iteration 39 — proposal

**Module:** BEAR

**Claim:** The BEAR bleed is an EXIT-latency problem, not an entry-regime problem: the dominant loss channel is 46 SIGNAL_EXIT shorts at -12.55% (vs only -3.22% from 3 stops), meaning shorts are held while the tape recovers and are only closed by a lagging reversal signal. Seeding the BEAR exit with early momentum-reversal covers (price reclaiming a fast EMA, MACD histogram flipping positive, or RSI recovering) will clear the walk-forward fit gate (score > 0.0209, best-known BEAR) and, on the forward windo

**Killed by:** Refuted if the fit fails to clear 0.0209 (as every restrictive entry gate did), OR if the forward window opens but SIGNAL_EXIT loss is no better than -12.55%, win rate stays at or below 27%, and forward return does not exceed -7.11%.

Three consecutive BEAR attempts — H-L032 (200-EMA/50-200 cross downtrend gate), H-L033 (adx>25 AND di_minus>di_plus AND supertrend-bearish chop filter), and H-L038 (short-from-upside-extension) — all returned the IDENTICAL failing fit score -0.10078365375034581 and never opened a forward window. Three distinct restrictive entry gates collapsing to one degenerate no-trade fit is decisive evidence that adding AND-conditions to BEAR ENTRY starves the search; that direction is dead and should be abandoned, not deepened. What has never been attacked directly is the exit, even though the diagnosis is unambiguous: SIGNAL_EXIT is -12.55% across 46 trades while STOP_LOSS is only -3.22% across 3. H-L032 explicitly asserted this was 'not an exit problem' and was refuted, so the exit lever is both open and unfalsified. These seeds cover the short as soon as upward momentum returns (fast-EMA reclaim / MACD flip / RSI recovery) instead of waiting on the lagging signal that currently bleeds the 46 losers, and they use two-to-three joined comparisons rather than an overfit gate.

- `(close crosses above ema_9 OR macd_hist crosses above 0 OR rsi_14 > 55)`
- `(close crosses above ema_21 AND rsi_14 > 50)`