---
id: liquid-ml-research
title: "Liquid-universe and model-led research"
status: active
priority: critical
oneliner: "Replace infrastructure-only strategy cycling with liquid-universe, model-led, economically testable research."
modules: [quantlab, design, tests]
target: "continuous"
created: 2026-08-01
updated: 2026-08-04
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
- #QUANT5 pending — expose timeframes and make market-data ingestion incremental.
- #QUANT6 pending — separate live backtest, data and multi-agent work telemetry.
- #QUANT7 pending — run substantive strategy deliberations on the public agent Wall.
- #QUANT8 in progress — remove the sizing lookahead and rank strategies against a benchmark.
- #QUANT9 complete — SuperTrend+ADX (H-STA-001) tested on both the wrong scope (S00820, daily/386-asset, -7.57%) and, after a per-family data-override fix, the corrected one (S00826, 15m/BTC-ETH-BNB, -14.12%, vs +1950% buy-and-hold). No edge on either scope; not promoted.
- #QUANT10 complete — Donchian/Turtle breakout (H-DONCH-001): Phase-1 -4.69% over 1,929 trades (S00840). High activity, no edge; not promoted.
- #QUANT11 complete — multi-factor vote (H-MULTI-001): the best Phase-1 result this lab has produced, +36.97% / 16.0% DD / 2,195 trades / walk-forward profitable in 8 of 12 folds (S00841). Forward 2026: **-9.57% over 527 trades**, versus -22.6% equal-weight — positive alpha, negative absolute return. Not promoted.
- #QUANT12 complete — two-part regime-switching strategy (H-REGIME-001): Phase-1 -8.46% with a 23.97% drawdown that nearly tripped the 25% abort (S00845). The two-branch structure the operator asked for does not work in its simplest 200-SMA form; reported as-is rather than re-tuned until it passed.
- #QUANT13 in progress — the missing baseline (H-SMARSI-001): two SMAs and one RSI on hourly majors, binary confidence so all sizing belongs to money management, plus a 99-point parameter grid on pre-2026 BTCUSDT. Also fixes a real bug where `forward.py` ignored `FAMILY_DATA_OVERRIDES` and would have forward-tested an intraday family on the daily 386-asset universe.
