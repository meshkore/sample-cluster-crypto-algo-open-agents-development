# System 12 - results

## Per calendar year (each year from the same capital; each year traded with the 20 configurations chosen only on the years before it)

| era | year | System 12 | max DD | invested (avg) | System 11 | BTC |
|---|---|---|---|---|---|---|
| research | 2020 | -49% (chosen on 2019 alone) | 73% | 88% | +59% | +302% |
| research | 2021 | +115% | 23% | 67% | +96% | +60% |
| research | 2022 | -23% | 36% | 54% | -12% | -64% |
| research | 2023 | +35% | 14% | 54% | +38% | +156% |
| research | 2024 | +18% | 37% | 63% | +19% | +121% |
| research | 2025 | +9.7% | 20% | 43% | +7.8% | -6% |
| forward | 2026 YTD | +5.9% | 13% | 34% | +1.7% | -5% |

- **2021-2025:** +23.5%/yr, max DD 42%.
- **The frozen book** (chosen on 2019-2025), in-sample: 2019 +5%, 2020 +76%, 2021 +29%, 2022 +6%, 2023 +43%, 2024 +56%, 2025 +22%; DD 20%.
- **Paper:** $50k from 2026-10-21 16:00 UTC (`research/system12/paper/state.json`).

## Configuration (frozen, `research/system12/paper/selection.json`)

The average of 20 rules. Mostly: long BTC+ETH while (BTC 60-day momentum AND BTC above its 100/150-day average) or similar trend pairs; half short BTC+ETH when the regime is bearish; 40% volatility target.

## Log of actions

| date | action | result |
|---|---|---|
| 2026-10-21 | Opened after Classics 11 (the BTC-gated basket matched System 11) | operator go |
| 2026-10-21 | Step 1: long-only regime search, 13,552 configs | walk-forward 2025 -5%, 2026 +0.7%: not better than System 11 |
| 2026-10-21 | Step 2: long + short on perps, 75,504 configs | walk-forward 2025 +9.7%, 2026 +5.9%: adopted |
| 2026-10-21 | Paper book, $50k, frozen 20 configs, every 4 h | running (task `system12-paper`) |
| 2026-10-21 | System 11 stopped; the machine and the Live view moved to System 12 | done |
| 2026-10-21 | Bigger random search (lab12, 48 signals, 10 workers) | 2026 -15% walk-forward after 14,000 configs: stopped |
| 2026-10-21 | Review brief round 4 (System 12) published | https://quantlab-architecture.rjj.workers.dev/architecture |
| 2026-10-21 | Handover check: task `system12-paper` had never fired; started it once by hand | exit 0, `state.json` updated 17:17 UTC, 2 decisions logged; `paper.log` is UTF-16 with numpy warnings only |
| 2026-10-21 | Live view cleanup: tab "Training" -> "System 12"; Machine box and workers shown only while a lab12 worker is alive; Trading tab (System 10 paper + mirror) removed; `#/strategies/<id>` deep links fixed | Playwright: no page errors; Strategies -> system12 renders Log, Results, Theory |
| 2026-10-21 | Public page hung on reload: `cf_pusher` timed out (25 s) on its ~7 MB first push and then marked the page as published | timeout 120 s; failed parts are retried. The running copy (elevated, launched by the watchdog) keeps the old code until it is next relaunched |
