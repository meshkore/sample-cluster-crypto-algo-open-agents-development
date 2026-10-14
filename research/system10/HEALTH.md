# System 10 — market health (2026-10-14)

A safety model apart from the trading system: `system010_conditioned_rl/health.py`. No fitting.
**Market score 0–100** (the green→red bar; healthy ≥ 60, caution ≥ 40, danger below) from five
components on the 14 coins' 15m closes: crash speed (1h/4h/24h drop of BTC or the coin index in
sigmas), 7-day trend, volatility spike, breadth of the fall, correlation on down days.
**Book score**: the paper book's last 20 trades closed within 14 days (hit rate, losses in a row,
summed return). Live: `python -m system010_conditioned_rl.health --loop` → `paper/health_state.json` (~4 s).

## Backtest — release 31, walk-forward signals, chosen on 2020–2025 only
Study: `tools/health_study.py` (63 settings, `rnd/health_study.json`). Return / max DD per year.

| setting | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | CAGR | worst DD |
|---|---|---|---|---|---|---|---|---|
| no guard | +2.6 / 36.5 | +34.5 / 39.0 | +29.1 / 16.0 | +17.5 / 3.5 | +47.8 / 22.6 | +30.6 / 22.6 | +26.2 | 39.0 |
| market < 10 → block | +16.2 / 30.4 | +23.6 / 43.9 | +37.0 / 12.9 | +2.7 / 3.5 | +28.7 / 22.7 | +11.9 / 18.4 | +19.5 | 43.9 |
| market < 10 → flatten | +10.7 / 32.5 | +24.3 / 43.6 | +37.4 / 12.9 | +2.7 / 3.5 | +27.6 / 22.8 | +17.7 / 16.6 | +19.5 | 43.6 |
| market 1-day mean < 20 → flatten | +14.8 / 31.2 | +19.8 / 45.5 | +29.4 / 12.9 | +17.4 / 3.5 | +41.6 / 22.6 | +22.1 / 22.6 | +23.9 | 45.5 |
| **book < 40 → flatten, resume ≥ 50** | +28.8 / 16.7 | +56.4 / 28.4 | +15.2 / 16.4 | +17.5 / 3.5 | +58.8 / 16.0 | +56.8 / 13.7 | **+37.6** | **28.4** |
| book < 40 → block only | +21.8 / 20.5 | +53.1 / 33.9 | +22.4 / 16.1 | +17.5 / 3.5 | +28.8 / 25.7 | +7.6 / 15.4 | +24.5 | 33.9 |

- **Market halts cost money.** Release 31 buys the capitulation bar: its best 2023 trades were
  entered on the bar the score hit 0 (2023-06-10, 2023-08-17). Every market-score guard lost return.
- **Book losing-streak breaker** (flatten) won 2020–2025 at every threshold tried (10–70: CAGR
  +26..+38%, DD 28% vs 39%). Max profit = optimal (Q 0.50 vs 0.18). No setting holds 2021 under 25%.
- **2026, read once:** no guard +22.4% / DD 17.3%; guard **+9.1% / DD 8.4%** (16 halts, flat half
  the year). Drawdown halved, return more than halved (Q 0.10 vs 0.29). Not confirmed.

## Crash episodes (score low; first < 25; book over the window: no guard → book guard)
COVID 2020-03: 0, 03-08 (BTC peak day) — −28.4% → −12.1%. May 2021: 4, 05-12 — −9.1% (DD 37%) →
−11.1% (DD 16%). LUNA 2022-05: 3, 05-05 — +2.9% both. 3AC 2022-06: 11 — −2.5% both. FTX 2022-11: 1,
11-07 — −0.3% → −13.1%. 2024-08-05: 0, 08-04 — −0.8% (DD 14%) → 0%. 2025-10-10: 0, same evening —
+5.5% (DD 14%) → +1.7% (DD 1%). The score falls to danger before or at the low every time.

## Decision
Indicator **on** (live bar). Guard = book < 40 → halt, **advisory only** (`enforced: false`); the
paper book is not stopped. Revisit with more 2026 trades.
