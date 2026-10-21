# System 10 - results

Release 31 (2026-10-11), the live release: BTC vs its 100-day average, breadth up 0.5 / down 0,
AI selector, AI exit (max 768 bars), 0.75x when falling, full feature set, 5 slots, stop 12%,
stake by signal (1%), drawdown-scaled stakes (35%), scale in/out.

## Unseen years (walk-forward: models fitted on years < N)

| year | return | max drawdown | trades | win rate |
|---|---|---|---|---|
| 2022 | +29.1% | 16.0% | 327 | 54% |
| 2023 | +17.5% | 3.6% | 86 | 78% |
| 2024 | +47.8% | 22.6% | 1,677 | 60% |
| 2025 | +30.6% | 22.6% | 1,447 | 51% |

Worst year +10.3% (second seed set), CAGR +30.8%, max DD 24.7%. Maximum-profit configuration:
CAGR +35.1%, worst year +7.6%, DD 23.7%.

## 2026 - forward only, never used to choose

+22.4%, max DD 17.3%, 1,477 trades, win rate 43% (reading of 2026-10-13).
Paper book from 2026-10-13 20:00 UTC, stopped 2026-10-21 (see the log below).

## Log of actions

| date | action | result |
|---|---|---|
| 2026-10-21 | Paper book stopped (`research/system10/jobs.json` `"paper": false`); the Trading tab removed from the page | last state: equity $49,990, flat; the BingX shadow mirror (shadow, 0 positions) untouched, it holds while the paper book is stale |
