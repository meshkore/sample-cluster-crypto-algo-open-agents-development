## Iteration 20 — proposal

**Module:** BULL

**Claim:** A deliberately permissive two-condition BULL long entry — close > sma_50 AND macd_hist > 0 (trend + positive momentum) — will move the 2026 forward trade count off the frozen 71 by contributing at least one BULL-routed long trade in the forward window.

**Killed by:** The forward trade count stays exactly 71 (all-BEAR) with forward return unchanged at -0.0782. That would prove the DETECTOR never routes any forward bar to the BULL branch, so no BULL rule change can affect forward return — BULL rule-space is dead and effort must move to the DETECTOR breadth axis.

This is a reachability probe, not another quality-gate attempt. H-L010 (close>ema_200 AND di_plus>di_minus, three conditions) and H-L015 (high_55 breakout AND adx>25 AND chaikin_money_flow>0) both rewrote the BULL entry with genuinely distinct mechanisms, and both left the forward output bit-identical: 71 trades, -7.82%. That is the actual signal in the ledger — the BULL branch contributes zero forward trades regardless of what its entry says. H-L016 corroborates the mechanism from the other side: the DETECTOR routes all 71 to BEAR because bull_breadth (0.416) ≈ bear_breadth (0.413), so the bull regime never wins the label. Every prior BULL hypothesis asked 'does a better long gate beat incumbent?' and got a frozen 71; none isolated the prior question, 'is the BULL branch reachable at all?' A maximally permissive trend+momentum gate is the sharpest test of that: close>sma_50 fires on roughly half of all bars, so if the branch is reachable the count MUST move off 71. If even this cannot, reachability is falsified conclusively and the correct conclusion is to abandon BULL rule-space entirely and attack the DETECTOR's non-discriminating breadth axis (per H-L016) instead of deepening it further.

- `(close > sma_50 AND macd_hist > 0)`