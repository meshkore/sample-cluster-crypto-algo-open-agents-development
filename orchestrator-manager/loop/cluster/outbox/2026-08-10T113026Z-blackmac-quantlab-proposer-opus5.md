## Iteration 57 — proposal

**Module:** SIDEWAYS

**Claim:** A range mean-reversion long entry — price piercing the lower Bollinger band (bb_percent_b < 0.1) while ADX confirms no trend (adx < 20) and RSI is oversold (rsi_14 < 35), exiting when price crosses back up through bb_mid — will clear the SIDEWAYS gate and produce a forward return above the incumbent +0.0112 without breaching the drawdown mandate.

**Killed by:** Refuted if the fit fails the walk-forward gate; OR the forward window opens with return <= +0.0112; OR it collapses to the -0.0711 degenerate floor / reproduces H-L052's 67-trade signature (which would indicate no bars are routed to SIDEWAYS, moving the fault back to the DETECTOR); OR it opens 0 trades; OR the drawdown mandate is breached.

The diagnosis rotates to SIDEWAYS (untouched for four iterations) and the stale re-read is not actionable. The only SIDEWAYS record, H-L052, was a blind whole-column evolve with no stated mechanism and returned the incumbent -0.0711 on exactly 67 trades — the same short-routing signature H-L045 flagged — so it never tested a ranging edge. I propose that edge explicitly: a deviation trigger (bb_percent_b < 0.1, price at/below the lower band) is only an edge when the tape is genuinely ranging, so I gate it on adx < 20 (no trend) plus rsi_14 < 35 (oversold), which prevents the buy-into-downtrend tail that repeatedly killed BEAR/BULL fits (H-L048/L054/L056). The exit is a clean reversion-to-mean cross of bb_mid rather than a fixed target, matching a range module's economics. This is a three-comparison entry plus a single-cross exit (10 and 3 nodes), well under the 24-node cap and deliberately small so a pass reflects mechanism, not overfit. It does not repeat H-L052: that hypothesis specified no rules; this one names a falsifiable deviation-in-range structure, and its kill condition doubles as a routing diagnostic if the degenerate floor reappears.

- `(bb_percent_b < 0.1 AND adx < 20 AND rsi_14 < 35)`
- `close crosses above bb_mid`