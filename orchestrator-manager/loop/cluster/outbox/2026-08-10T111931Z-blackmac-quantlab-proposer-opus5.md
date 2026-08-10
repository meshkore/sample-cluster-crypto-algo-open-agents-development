## Iteration 57 — proposal

**Module:** SIDEWAYS

**Claim:** The SIDEWAYS module loses because it fades band extremes without first confirming the absence of a trend, so its mean-reversion entries fire inside directional moves and inherit the same degenerate -7.11% floor. Gating entries on a genuine no-trend regime (adx below 20) and only then fading the Bollinger extreme (bb_percent_b in the outer decile) with an oversold/overbought RSI confirmation will open a forward window returning above the incumbent +1.117% without breaching the drawdown mandate.

**Killed by:** Refuted if the adx-gated fade either fails the walk-forward gate, opens no forward window (0 trades), or opens one whose return is ≤ the incumbent +0.01117 — in particular if it collapses back to the -0.0711 degenerate floor, proving the edge was never a regime-conditioning problem.

H-L052 already refuted a blind 'evolve SIDEWAYS rules' pass — it returned the identical -7.11% floor on 67 trades, the same number and return that DETECTOR arbitration defects (H-L045/L051/L052) produce, which tells me the evolved SIDEWAYS entries were firing in the same trending bars the other modules fight over rather than in real ranges. This is NOT a repeat of H-L052: instead of evolving over all served columns, I isolate the one mechanism a range trader depends on — regime confirmation. ADX below 20 is the textbook no-trend gate; only inside that regime does fading bb_percent_b outer-decile extremes with an RSI_14 confirmation have positive expectancy, because outside it the fade is knife-catching a trend. The 'deviation' rule family is the natural fit and each seed is a compact 3-comparison conjunction (~10 nodes), symmetric long/short, well under the 24-node cap and free of any self-comparison. If this still yields the -7.11% floor, the defect is arbitration in the DETECTOR, not SIDEWAYS, and this direction should be abandoned rather than deepened.

- `(adx < 20 AND bb_percent_b < 0.15 AND rsi_14 < 35)`
- `(adx < 20 AND bb_percent_b > 0.85 AND rsi_14 > 65)`