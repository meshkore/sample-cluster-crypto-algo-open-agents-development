## Iteration 32 — REFUTED

**Module:** BEAR

**Hypothesis:** The BEAR bleed is an entry-regime problem, not a rule-search or exit problem: the 46 SIGNAL_EXIT losers (-12.55%) are shorts opened during pullbacks inside a structurally rising tape. Gating BEAR entries on a confirmed downtrend structure — close below the 200 EMA, the 50/200 EMA stack inverted (ema_50 < ema_200), and directional movement favoring sellers (di_minus > di_plus) — will lift BEAR win rate above 35% (from 27%) and shrink the SIGNAL_EXIT loss materially, because shorts will no longer 

**Fit:** score -0.10078365375034581

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score -0.10078365375034581, best known for BEAR 0.0209); the forward window was not opened.

- entry_rule: `(close < ema_200 AND ema_50 < ema_200 AND di_minus > di_plus)`
- exit_rule: `high crosses below low*1.0745`