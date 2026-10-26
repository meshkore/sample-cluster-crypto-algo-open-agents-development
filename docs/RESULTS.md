# System 12 - results and log of actions

## Walk-forward record (each year traded with what was chosen on earlier years only)

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| System 12, champion v6 (book + G00233) | +148% | -13% | +48% | +25% | +9% | live page |
| the frozen book alone (20 members) | +115% | -23% | +35% | +18% | +10% | live page |
| BTC | +60% | -64% | +156% | +121% | -6% | live page |

Source: `system12/record.json`. Chain drawdown 2021-25: 42% for the frozen book.

## Paper books

| book | from | status |
|---|---|---|
| frozen book (20 members, no overlays) | 2026-10-21 16:00 UTC | stopped 2026-10-25 at -3.1%; archived |
| champion v6 (the system) | 2026-10-22 16:00 UTC | running, `system12/paper.py`, every 4h |

## Log of actions

The full research log for 2026-10-21 to 2026-10-25 (tasks 1-23, the hypothesis loop, every refuted idea) is in the archive:
`meshkore-crypto-archive/systems/system012_btc_regime/docs/RESULTS.md`.

| date | action | result |
|---|---|---|
| 2026-10-21 | System 12 opened: a long/short regime search over 75,504 configurations, walk-forward | 2025 +9.7%, 2026 +5.9%: adopted. Frozen paper book of $50k |
| 2026-10-21 to 10-24 | Hypothesis loop: 15,288 tests against the frozen book | one robust adoption: G00233 (trailing stop on shorts + convex trend sizing) = champion v6 |
| 2026-10-23 | Long-history checks: BTC 2014-2026, ETH 2018-2026, cost and funding stress | v6 holds: 12 of 13 BTC years positive, survives double costs |
| 2026-10-23 to 10-25 | Regime switcher, hourly event edges, neural net on hourly perps, combinations with E1 | none beats the book walk-forward |
| 2026-10-25 | Operator: "clean up: one system, one version". The repository was reduced to System 12 champion v6 (`system12/`). Everything else moved to `meshkore-crypto-archive/` and the data to `meshkore-crypto-data/`, outside the repo. The hypothesis loop, legacy watchdogs, the System 10 BingX mirror (unarmed) and the frozen paper book were stopped | the new package reproduces the old engine's weights exactly on every bar since 2023-06; earlier differences come from days the old 15m data had dropped. Funding now comes from Binance live (the old cache stopped at 2025-12-31) |
| 2026-10-26 | Code audit before the repository goes public: engine split into config, data, market, strategy, backtest and paper modules; pages moved to `system12/web/`; tests per module; history scanned for credentials | weights and returns identical to the previous version on every bar; no credential found in the git history; 14 tests pass |
