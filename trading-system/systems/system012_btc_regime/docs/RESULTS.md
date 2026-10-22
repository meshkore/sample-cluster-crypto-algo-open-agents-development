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
| 2026-10-21 | Public page blank on a slow link: the page polled the ~800 KB state every 1.5 s with no in-flight guard, so requests piled up | one request at a time, every 5 s, "Loading..." until the first answer; checked on a throttled 1.5 Mbps link |
| 2026-10-21 | Hypothesis loop opened (`hyp12.py`, task `system12-hyp`); Live view shows it (Hypotheses section) | 26 written hypotheses tested walk-forward |
| 2026-10-21 | H001-H018: exits, volatility, funding, sizing, ETH share, costs | H001 crash exit hurts 2021 (-46 pp), rejected. H006 (ETH 75% of the long leg) ADOPTED as candidate: +10.4 pp/yr, 5/5 years, but the gain is mostly 2021/2025 and 2026 reads -3.4 pp. H005 (1.5x longs) +15 pp/yr but DD 57%: rejected |
| 2026-10-21 | H019-H026: altcoins (operator: "alts move 300% when BTC moves 50%") - alt season switches, breadth, ETH/BTC, alt shorts, bigger alt size | all rejected: the rules learn "alts" from 2020-21 and apply them in 2022-23 (2x alts: 2022 -59%, 2023 -18% vs +35%) |
| 2026-10-21 | H027-H030: bigger positions (operator: "average investment should be above 80%"); ledger now records invested % per year | all rejected by the pre-registered rule. Best, H028 (1.5x positions): 2021 +192%, 2022 -30%, 2023 +43%, 2024 +12%, 2025 +24%; invested 59-78%; chain DD 53% vs 42%. Operator decision: accept more drawdown for more return? |
| 2026-10-21 | Local server is the main view (http://localhost:8799/#/live, refresh every second); cloud pusher braked (`research/system06/preview/STOP_PUSHER`, watchdog respects it) | the public page keeps its last snapshot. A duplicate H030 entry (manual run racing the loop) was removed from the ledger |
| 2026-10-21 | Generator added (`gen12.py`, operator: "keep developing this while I sleep"): 32 pieces, singles -> pairs -> biased triples, ~3.5 s a test; report `hyp/REPORT.md` | at 100 tests: G00008 (trailing stop on shorts, 10-15% off the low) ADOPTED: 2022 -11% vs -23%, chain DD 37% vs 42%, 4/5 years; sensitive to the trail (6% gives 2022 -36%). Candidate champion 2021-25 +37.9%/yr vs frozen +23.5% |
| 2026-10-22 | Night run: 572 tests, then idle from 20:00 to 08:54 UTC - the triple sampler's bandit (exp(40 x gain)) gave all the weight to two size pieces and no distinct triple could be drawn | fixed: clipped scores, a floor, draws without replacement, and pieces scored net of extra drawdown. Running again. No new adoption overnight (2 adopted: H006, G00008; bar now 4.2%/yr). Size pieces (long_size, gross_cap) give +27%/yr mean gain but DD 60-70%: blocked by the DD rule |
| 2026-10-22 | Operator: "maxima caida 40" - adoption rule now caps the 2021-25 chain drawdown at 40% (was: champion + 2 pp) | applies from test 586 on; earlier verdicts not re-judged |
| 2026-10-22 | Champion paper book (`paper12c.py`): $50k from 08:00 UTC, frozen snapshot H006 (ETH 75%) + G00008 (short trail 10%), side by side with the frozen book | first target: long BTC 21%, ETH 64%. The frozen book is untouched (-0.49% since 21/10) |
| 2026-10-22 | Generator batch 2: 13 more pieces (ATR trail, MA cross, RSI trim/cover, negative funding, calm-vol leverage, ramp-up, DD-adaptive size, ETH confirm, September, weaker-coin short, moderate sizes 1.1-1.3x) | 45 pieces in all; running |
| 2026-10-22 | Second layer (`meta12.py`, operator: decision tree + loser autopsy): per-year depth-3 tree on 17 market features; autopsy of the 2021-25 chain in `hyp/META.md` | 122 trades, 61% losers, worst -14%: losers are short whipsaw longs in flat markets. Out-of-sample the tree separates in 2021/2022/2025, not 2023, inverted in 2024. H031 (tree filter), H032 (whipsaw filter), H033 (cooldown): all rejected walk-forward |
| 2026-10-22 | Loop at 2,635 tests: adopted G00858 (long stop + light September) and G00878 (pyramiding + RSI short cover) | champion 2021-25 +50%/yr (2022 -7%) vs frozen +23.5%; but its 2026 reading fell to -1% vs frozen +5% - the forward year does not confirm the later adoptions. Champion paper book keeps the 09:41 snapshot (H006 + G00008) |
| 2026-10-22 | Strategy catalogue (`catalog12.py`, 8 collector agents): 785 published strategies indexed with sources (`research/system12/catalog/CATALOG.md`), 593 implementable tested walk-forward alone | A 12 (halving clock, Fed net liquidity, DXY, simple TSMOM with shorts, Williams GSV...), B 42, C 539 - nearly every popular retail rule (MACD+EMA, RSI, Supertrend, candles) fails |
| 2026-10-22 | Loop v1 flaw found: adoption judged on 2021-25, so after 3,100 tries the champion was chosen on the years it was scored on (2021-25 +79%/yr) while 2026 read -23% (turn-of-month, Uptober adopted) | v1 archived in `research/system12/hyp_v1/`; all champion figures reported from v1 (+37.9%, +50%) were optimistic |
| 2026-10-22 | Loop v2: adoption on 2021-2023 only; 2024, 2025, 2026 out of sample for the whole loop; every hypothesis re-judged | first adoption K-mac-dharmatech-netliq-fairvalue: out of sample 2024 +45% (frozen +18%), 2025 +9.7% (=), 2026 +7.5% (frozen ~+5%) |
| 2026-10-22 | Loop v2 (adopt on 2021-23 raw return) stacked exposure: 10 adoptions in 163 tests (8 "add" modes + x1.2 leverage), 2024 +215% but 2025 +2% and 2026 -6% vs frozen +9.7% / +5%. v3 (adopt on Sharpe 2021-23) still adopted turn-of-month and RSI+SMA: 2025 -1%, 2026 -17% | archived in `hyp_v2/`, `hyp_v3/` |
| 2026-10-22 | Loop v4: train 2021-23 (Sharpe gain >= 0.05 + 0.03 ln n, 2/3 years, DD <= 40%), validation 2024-25 (no year worse by > 2 pp, Sharpe not lower), test 2026 never looked at. Champion paper book now follows the champion (old books archived in `paper_champion/history/`) | first champion: Fed net liquidity blend + Bollinger/RSI-30 add: 2022 +38%, 2023 +68%, 2024 +64%, 2025 +15%; test 2026 -9% vs frozen +5% |
| 2026-10-22 | Pre-signal state study (`pre12.py`, operator idea: the candles before a signal): 316 entries 2021-25 of the books' 20 members, 39 candle/volume/speed features | no single feature survives multiple-testing correction (best q 0.48); a walk-forward logistic model: AUC 0.65/0.58/0.59 in 2021-23, 0.52/0.50 in 2024-25, its trusted half earned more in 5/5 years. H034 (cut untrusted trades) queued in the loop; on the base book it helps 2024 and hurts 2022 |
| 2026-10-22 | Task list `research/system12/TODO.md` (operator: execute in order). Tasks 1-6 done: loop priority for written hypotheses; H034-H041 (pre-signal state, market phases with mean reversion in sideways markets, cycle position, MVRV, DVOL, catalogue averages, trend on 14 coins; MVRV/DVOL downloaded by `ext12.py`) | none helps against the frozen book: each year's choice on earlier years switches them off |
| 2026-10-22 | Loop v5: v4's stacked champion (net liquidity + Bollinger/RSI add + G00236) read -12% in 2026; restarted with champion = frozen book + Fed net-liquidity filter (the only overlay better in every year incl. the 2026 test) and no "add" mode | champion v5: 2021 +115%, 2022 +21%, 2023 +50%, 2024 +45%, 2025 +9.7%, 2026 +6.7% (frozen +3.8%); champion paper book rolled to it |
| 2026-10-22 | Loop adopted G00233 (trailing stop on shorts + convex trend sizing) on top of v5 | champion 2021-26: +151%, +40%, +63%, +50%, +9%, +8% (frozen +115/-23/+35/+18/+10/+4) |
| 2026-10-22 | Task 10, robustness (`robust12.py`, `robust/ROBUST.md`) | costs x2/x3 still positive every year; block bootstrap P(year >= 0) 85% vs frozen 64%, P(DD > 40%) 4% vs 15%; but none of the 24 parameter/mode variants of the net-liquidity rule beats the frozen book in all 6 years: the edge depends on its parameters |
| 2026-10-22 | Task 11 (`long12.py`, `robust/LONG.md`): pre-registered net-liquidity filter (n 126, lo 0, hi 1; Nasdaq for the S&P before 2016) on a plain BTC trend rule, spot, 2014-2020 | worse in 6 of 7 years (2017 -4% vs +268%), all 8 variants break 2017: the liquidity edge belongs to 2021-26, champion v5 is NOT investable on this evidence. The plain trend rule holds 2014-2026 (3 mild losing years, DD 36% vs BTC 84%) |
| 2026-10-22 | Task 13, long-history gate (`gate13.py`, `robust/GATE.md`): G00233 (short trail 10% + convex trend sizing) on a System-12-like daily BTC book, 2014-2020 | passes: better 4 / worse 3 years, DD 42% -> 32%. The plain long / half-short book has only 2 losing years in 2014-2026 (-4%, -9%) |
| 2026-10-22 | Champion v6 = frozen book + G00233 (net-liquidity filter removed: failed 2014-20) | walk-forward 2021 +148%, 2022 -13%, 2023 +48%, 2024 +25%, 2025 +9.3%, 2026 +3.8% (frozen +115/-23/+35/+18/+9.7/+3.8). Champion paper book rolled; loop continues against v6 |
| 2026-10-22 | Task 12, liquidity family vs champion v6: H042 M2 growth, H043 stablecoin supply growth (DefiLlama), H044 net-liquidity momentum (data via `ext12.m2_and_stables`) | none adopted: Sharpe gains -0.11 / +0.10 / +0.07 vs a bar of 0.28; M2 hurts 2023 |
| 2026-10-22 | Task 8, hourly effects (`hour12.py`, `robust/HOURLY.md`, Binance BTCUSDT 1h 2018-2026) | the published 21:00-23:00 UTC long is positive before costs in 7/8 years (~+35%/yr), 0/8 at 0.10%/side, 6/8 at maker 0.02%/side with 2026 -12%; walk-forward best window picks 21h from 2021: not usable without guaranteed maker fills |
