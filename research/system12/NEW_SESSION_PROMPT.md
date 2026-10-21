You are taking over the crypto research lab in `meshkore-crypto-cluster` (Windows, Git Bash + PowerShell). Start clean: do not rely on older memories about Systems 06-11 unless the repo confirms them.

**Read first, in this order (about 10 minutes):**
1. `.meshkore/context/overview.md`: where the project is.
2. `research/system12/README.md`: the ONLY active system, what runs, the files, the technical debt, the agreed method.
3. `trading-system/systems/system012_btc_regime/docs/SUMMARY.md` and `RESULTS.md`: its record and dated action log.
4. `trading-system/systems/system011_xs_ranking_pit/docs/SUMMARY.md`: why System 11 was closed and what NOT to repeat.

**State (2026-10-21).**
- **What System 12 does:** long BTC+ETH in BTC bull regimes, half short on USD-M perps in bear regimes, 40% volatility target. The book is the average of 20 rule combinations, frozen in `research/system12/paper/selection.json`.
- **Walk-forward** (each year chosen only on earlier years): 2021 +115%, 2022 -23%, 2023 +35%, 2024 +18%, 2025 +9.7%, 2026 YTD +5.9%.
- **Paper book:** $50k since 2026-10-21 16:00 UTC; Windows task `system12-paper` runs every 4 h. No real money.
- **Live page:** https://quantlab-public-mirror.rjj.workers.dev/#/live (Training and Trades tabs) and the Strategies tab (one record per system). The frontend is `research/system06/preview/dashboard.html`, its data comes from `mock_server.py`, and `cf_pusher.py` publishes it. The review brief: https://quantlab-architecture.rjj.workers.dev/architecture (`research/architecture_brief/`).

**Working rules from the operator:**
- Reply in Spanish, briefly: under five lines, a small table if needed, details in the repo or page with a link. Code, comments and docs are in English.
- One written hypothesis at a time, tested walk-forward against the frozen book, adopted only if it wins out of sample. NO mass searches: Bayes 11, Rocket 11 and lab12 all produced in-sample winners that failed walk-forward.
- 2026 is read, never used to choose. Do not touch the paper book's frozen selection.
- Never arm, widen or touch the BingX live mirror (`live-trading/`). Never print credentials (`~/.cf_deploy_env` and similar live outside the repo).
- Page: less content, more perfect. Tiles with a number and a few words, no text blocks.
- Record every action in the system's `docs/RESULTS.md` "Log of actions" and keep `context.json` / `SUMMARY.md` consistent. `trading-system/tests/test_system_docs.py` must pass.

**Open decisions for the operator (ask, do not decide):**
1. CLAUDE.md "Project rules" say "long-only" and "abort at 25% drawdown". System 12 shorts on paper (approved 2026-10-21), and its walk-forward chain hit 42% DD in 2022. Should the rules text be updated?
2. Legacy infrastructure still running:
   - `system06-watchdog`: the pusher and the wall listener (needed), plus System 06/10 legacy loops;
   - `plan-v2-forward-ic`: System 11's paper book, kept as a yardstick.

   Keep or stop?
3. The first improvement hypothesis to test. Suggested: make 2022 less bad with a faster regime exit in crashes. Write it down before testing.

Start by confirming the paper book is updating (`research/system12/paper/state.json`, `paper.log`). Then give the operator a 3-line status and ask decision 3.
