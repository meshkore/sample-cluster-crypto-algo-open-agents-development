---
id: liquid-ml-research
title: "Liquid-universe and model-led research"
status: active
priority: critical
oneliner: "Replace infrastructure-only strategy cycling with liquid-universe, model-led, economically testable research."
modules: [quantlab, design, tests]
target: "continuous"
created: 2026-08-01
updated: 2026-08-05
owner: codex-lead
related: [public-state-mirror]
---

## Why this exists

The observed forward result is not evidence of a useful strategy. Research must
use a liquid and capacity-aware universe, explicit signal diagnostics, risk-aware
portfolio construction, and a genuine model-selection process before promotion.

## Task plan

- #QUANT1 complete — audit found rejected experiments reaching forward and binary signal confidence.
- #QUANT2 in progress — liquid/capacity gates are live; model-led candidates remain next.
- #QUANT3 pending — add independent Codex/Claude reviews and evidence gates.
- #QUANT4 complete — persistent champion record, decision ledger and populated public view.
- #QUANT6 pending — separate live backtest, data and multi-agent work telemetry.
- #QUANT7 pending — run substantive strategy deliberations on the public agent Wall.
- #QUANT8 in progress — remove the sizing lookahead and rank strategies against a benchmark.
- #QUANT9 complete — SuperTrend+ADX (H-STA-001) tested on both the wrong scope (S00820, daily/386-asset, -7.57%) and, after a per-family data-override fix, the corrected one (S00826, 15m/BTC-ETH-BNB, -14.12%, vs +1950% buy-and-hold). No edge on either scope; not promoted.
- #QUANT10 complete — Donchian/Turtle breakout (H-DONCH-001): Phase-1 -4.69% over 1,929 trades (S00840). High activity, no edge; not promoted.
- #QUANT11 complete — multi-factor vote (H-MULTI-001): the best Phase-1 result this lab has produced, +36.97% / 16.0% DD / 2,195 trades / walk-forward profitable in 8 of 12 folds (S00841). Forward 2026: **-9.57% over 527 trades**, versus -22.6% equal-weight — positive alpha, negative absolute return. Not promoted.
- #QUANT12 complete — two-part regime-switching strategy (H-REGIME-001): Phase-1 -8.46% with a 23.97% drawdown that nearly tripped the 25% abort (S00845). The two-branch structure the operator asked for does not work in its simplest 200-SMA form; reported as-is rather than re-tuned until it passed.
- #QUANT13 complete — the missing baseline (H-SMARSI-001): two SMAs and one RSI on hourly majors. **S00848: Phase-1 +350.09% / 20.38% DD / 1,362 trades / walk-forward 9 of 12 folds, consistency 0.75 (best in the lab); locked 2026 forward -7.33% with +19.5pp excess.** 56 of 99 grid points profitable and all four held-out majors positive, so a region rather than a fitted corner — and still 1/33rd of buy-and-hold (+11,557%), which is recorded as the honest headline. Also fixed `forward.py` ignoring `FAMILY_DATA_OVERRIDES`.
- #QUANT5 complete — timeframes are exposed per family and market-data ingestion for override families is on-demand and cached (`FocusedDataset`), used identically by both phases.
- #QUANT15 in progress — the operator's four-piece system: a market-wide major-trend detector (`regime.py`, six-asset composite plus breadth, causal by construction and sabotage-verified against three deliberate lookaheads) and three regime-conditional branches behind a router (`regime_system.py`, family `regime_router`). Measured before tuning, and two of the premises failed: chasing rebounds in a bear market is the **worst** cell in the tactic table (-0.20% over 20 bars, versus +2.26% for the same bounce in a bull), and the best tactic barely differs by regime at all. **Phase-1 five-asset hourly basket: the router returns +211.2% at 20.16% DD against the control's +432.4% at 19.05% — 221 points given up for no drawdown reduction.** Every regime-aware arm loses to the plain rule; gating the control by regime is efficiency-neutral (39.6 vs 37.9 return per unit exposure), so the labels carry no exploitable information at this scope. Round 2 explored Kotegawa's (BNF) 25-day deviation rate on operator request: his real signal (buy 20-35% *below* the 25-day average) shows a **twelve-point regime-conditional spread** — +10.13% forward in BULL against -1.57% in BEAR — the first exploitable information the detector has produced. It does not survive to portfolio level for a capacity reason, not an edge one: per unit of deployed capital it matches the control (37.7 vs 37.9 return/exposure) but fires only 164 times in nine years across five majors. Also raised the drawdown abort 25% -> 30% and **found it changes almost nothing** (abort-only is bit-identical; the whole +1.5 to +3.2 points comes from the de-leverage ramp, now a separate parameter). The family is now a full member of the research pool, and **S00851 is published: +169.58%, 20.92% DD, 1,683 trades, walk-forward 6 of 12, -264.3 points against the control.**
- #QUANT14 in progress — restructured the measurement layer after QUANT13 showed the instrument, not the strategies, was the problem. Exposure (average/peak/time-in-market) is now a first-class output; exit distance is separated from position size, which made an entire region of the configuration space expressible for the first time (+31.58% -> +68.95% best reachable on BTCUSDT); and every evaluation now carries a cached control-group contrast against H-SMARSI-001 under identical bars, costs and policy. Recorded the decision that parameter selection happens at the deployment scope, after single-asset tuning produced a basket-illegal configuration twice in one day.
