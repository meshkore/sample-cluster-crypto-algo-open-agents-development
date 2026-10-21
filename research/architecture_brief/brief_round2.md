# Independent review request: crypto trading research, one page of context

You are an expert reviewer in quantitative finance, market microstructure, ML for trading and crypto. Below: what we tried, what broke, what runs now, and the latest results. We left out our own view of what to do next on purpose. Give us ideas we have not considered, including changing the problem.

## History, in brief

1. **2026-08 to 2026-10: System 06, then System 10.** 15-minute bars on 14 coins, long only. Small neural nets selected entries and forecast exits, with a rule book for sizing. About 25,000 configurations were searched and the best released. Paper trading on $50k started 2026-10-13.
2. **Round-1 reviews (2026-10-19) and a falsification plan.** We found these errors:
   - **Survivor universe.** The 14 coins were today's liquid survivors. On a point-in-time list (top 14 by turnover on 31 Dec of N-1, delisted coins included) the edge mostly vanished.
   - **Selection.** The release was the max of about 25,000 trials. PBO was 0.76. Re-seeding a configuration moved a year by a median of 7.7 points.
   - **Execution.** Decisions and fills were on the same close, with flat costs. With a fill at t+1, intrabar stops, a 0.45% round trip and square-root impact, the nested 2023-2025 return went from +25% / +59% (two seed sets) to -9% / -15%.
   - **No alpha.** Against an equal-weight basket, t < 2. No better than "hold the basket when BTC > its 100-day average".
   - **Add-ons.** About 40,000 filters and sizing rules (moving averages, RSI, MACD, macro, funding, martingale, conviction, rule mining) did no better than placebos.
   - Reinforcement learning and a learned bar-by-bar exit had failed earlier.
3. **New approach (since 2026-10-19).**
   - One model (ridge or gradient boosting, 28 causal features) ranks the point-in-time coins by expected forward return, on 4h and 1d bars.
   - Phase 4 risk layer:
     - 1% daily risk per position;
     - book volatility <= 2% a day;
     - correlation clusters capped at 40%.
   - Honest execution as above. Selection is always nested (chosen on years < N, then N read), on two seed sets, keeping the worse. DD <= 18%.
4. **Results of the new approach (2021-2025, out of sample):**
   - **The signal is real but small.** Cross-sectional Spearman IC against gross forward returns is 0.02-0.15, t > 2 in most years at 4h. Our first estimate was double that, because a cost term the features could predict sat inside the target.
   - **Long only:** no configuration holds DD <= 18% through 2021-2022. The risk layer cuts the median tail DD from 59% to 43% and lifts the median net 2022-2025 from -4% to +13%. Nested, worse seed set: -13.6%.
   - **Dollar-neutral long/short (perpetuals):** wins 2022 and 2025, loses the 2023-2024 rallies. Worse-seed Sharpe -0.06.
   - **Sealed 2026, one reading, frozen models:** only the 4h / 1-day horizon survives (gross IC 0.05, t 2.5). The top-3 minus bottom-3 spread is about 0 a day, far below cost.
   - **Forward arithmetic:** confirming a Sharpe near 1 at 2 sigma needs about 4 years of daily data.

## What runs now

- **Lab, 24/7.** It tests structural variants:
  - universe width: top 14 / 20 / 30;
  - venue: spot long, perpetual long, perpetual long/short (0.10% per side plus impact, funding charged);
  - target: pure cross-sectional ranking vs net of cost;
  - with and without funding features.
  Each variant sweeps 36 inner configurations, uses nested selection on two seed sets, and is then replicated on fresh seeds.
- **Gate for paper trading** (never capital directly): P(Sharpe <= 0) <= 0.05 / m (m = experiments so far), max DD <= 18%, at most one year in cash.
- **Path to capital:** months of forward evidence inside a bootstrap band, then 10% -> 50% -> 100%.
- **Forward tracker:** scores the frozen 4h / 1-day signal every 4 hours on a prospective window opened 2026-10-19.
- **Live status:** the "Plan v2" panel at https://quantlab-public-mirror.rjj.workers.dev/#/live

## Constraints

Retail book of $50k-$100k. Binance spot and USD-M perpetuals. 15-minute candles from 2019 with taker volume; funding history; a lagged macro panel. Costs as above.

## What we ask

1. With a real but small cross-sectional signal (IC about 0.05 at 1 day) and retail costs, is any construction tradeable? If not, say so plainly.
2. Which assumption would you change first: venue or fee tier, maker execution, holding period, universe breadth, target, or portfolio construction?
3. Which crypto signals or data with published out-of-sample evidence have we not tried, and how would you test them honestly here?
4. Is our validation too strict, too lenient, or wrong anywhere?
5. With forward tests this slow, what is a rational path to real capital, or a rational point to stop?

Be specific (papers, methods, parameters) and rank by expected value vs effort.
