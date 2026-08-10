## Iteration 22 — REFUTED

**Module:** BEAR

**Hypothesis:** The BEAR loss is an exit problem, not an entry problem: 48 SIGNAL_EXIT trades bleed -12.53% because shorts drift against a rising 2026 tape and are only flipped out slowly (STOP_LOSS fires just 4x for -4.25%, so losses accrue as slow signal exits, not gaps). Replacing the BEAR exit with a fast momentum-reversal rule — close the short the instant price reclaims the short-term mean (close cross_up ema_21) OR upward momentum turns positive (macd_hist > 0) — while restricting entries to an establish

**Fit:** score -0.10496605826798741

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score -0.10496605826798741, best known for BEAR 0.0209); the forward window was not opened.

- entry_rule: `return_20 > -0.0985`
- exit_rule: `(volume < volume_sma_50*1.9 AND mid_55 crosses below low_20 AND vortex_minus > 0.585)`