## Iteration 80 — INCONCLUSIVE

**Module:** SIDEWAYS

**Hypothesis:** Routing the H-L078B confirmed deviation-plus-volume mechanism into SIDEWAYS as its entry -- BUY (seed_rules[0]) when close pierces below bb_lower with heavy participation (volume_ratio_20 > 2.5), and SELL (seed_rules[1]) on reversion when close crosses UP through bb_mid -- returns positive forward and beats the incumbent's +0.20%, because the +48.3%/8yr the mechanism earned regime-agnostic (H-L078B) survived BEAR deployment at only -2.45% (H-L078), meaning the edge is carried by the non-bear bar

**Fit:** score -0.06378947343918467

**Forward 2026:** +0.20% on 148 trades

forward +0.20% on 148 trades, against incumbent +0.20%. The SIDEWAYS module took no trades in 2026, so this run measured the incumbent rather than the hypothesis: nothing about this direction was tested.

- entry_rule: `volume < volume_sma_20*sma_5`
- exit_rule: `natr_14 < 0.111`