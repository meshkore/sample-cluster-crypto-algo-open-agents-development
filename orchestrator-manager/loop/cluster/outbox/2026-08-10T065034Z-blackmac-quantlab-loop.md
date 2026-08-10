## Iteration 39 — REFUTED

**Module:** BEAR

**Hypothesis:** The BEAR bleed is an EXIT-latency problem, not an entry-regime problem: the dominant loss channel is 46 SIGNAL_EXIT shorts at -12.55% (vs only -3.22% from 3 stops), meaning shorts are held while the tape recovers and are only closed by a lagging reversal signal. Seeding the BEAR exit with early momentum-reversal covers (price reclaiming a fast EMA, MACD histogram flipping positive, or RSI recovering) will clear the walk-forward fit gate (score > 0.0209, best-known BEAR) and, on the forward windo

**Fit:** score -0.10078365375034581

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score -0.10078365375034581, best known for BEAR 0.0209); the forward window was not opened.

- entry_rule: `(close crosses above ema_9 OR macd_hist crosses above 0 OR rsi_14 > 55)`
- exit_rule: `((NOT (ema_9 crosses above ema_12) AND low < high*0.9555) AND (di_minus < 3.478 OR stoch_d < 86.216))`