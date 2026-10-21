# Independent review request: crypto trading research, one page of context (round 3)

You are an expert reviewer in quantitative finance, ML for trading and crypto. Below: what runs now, the results, and everything we tried in the last three days to improve it. Nothing has improved it reliably. Tell us why, and what you would do instead. Changing the problem is allowed.

## The system today: System 11

- **Universe.** A point-in-time top 14 coins by turnover on 31 Dec of the year before, delisted coins included. Binance spot, long only.
- **Model.** Small neural nets (MLP) on 28 causal features, 4h and 1d bars. The target is the coin's rank against the other coins over the next 1, 3 or 7 days.
- **Configurations.** There are 36 (timeframe x horizon x hold the top 3/5/8). For year N they are chosen only on years before N, and the 10 best are averaged ("the bag").
- **Exposure.** Scaled so the past drawdown fits an 18% budget; about 0.45x, so on average 15-25% of the capital is invested.
- **Execution.** Fills at the next 4h bar; 0.225% per side plus square-root impact; two seed sets, keeping the worse.
- **History.** Models trained on years < N only, from 2018. 2026 is a forward test, never used to choose.

| year | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 YTD |
|---|---|---|---|---|---|---|---|
| System 11 (paper scale) | +59% | +96% | -12% | +38% | +19% | +8% | +1.5% |
| BTC | +302% | +60% | -64% | +156% | +121% | -6% | -5% |

- **2020-2025:** +30% a year, Sharpe 1.4, max DD 25%.
- **Decay.** The edge fades: 2025 +8%, 2026 +1.5%.
- **The 2026 path:** Jan-Mar 0% (in cash while BTC fell 26%), Apr-Jun -3.8%, mid Jul-Oct +5.4% while BTC rose 33%.
- **Shape.** It defends well but captures little of the rallies.
- **Paper trading:** $50k since 2026-10-19.

## What we tried since round 2 (all honest: walk-forward, costs, worse seed set)

1. **Selection law.** Configurations are chosen by "positive every past year, better toward today" instead of Sharpe. The best law variant (top 20, perpetuals, ensemble) has Sharpe 0.75 vs 0.64 and fixes 2025 (+18% vs 0%). 2022 is still -14% everywhere. Recency-weighted training and a faster bear exit added nothing.
2. **Bigger positions.** The same signals at 1x to 4x the exposure:

   | exposure | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
   |---|---|---|---|---|---|---|---|
   | 0.45x | +35% | +47% | -7% | +27% | +14% | +2% | +2% |
   | 2x | +163% | +353% | -26% | +74% | +28% (DD 54%) | -4% | +6% |

   Size pays only in the 2020-21 bull years. Since 2023 it adds drawdown, not return.
3. **Moving-average exit** (sell below the EMA 20/50). Every variant lowers the return: EMA50 gives +25% vs +30% a year.
4. **Rocket 11.** About 4,500 rule ideas on top of the book, each against a time-shifted placebo:
   - coin, BTC, market and macro filters (Fed net liquidity, VIX, dollar, yields, Fear & Greed, credit), plus sizing and combinations;
   - the best combinations look huge in-sample (+40-68 points a year at equal risk);
   - walk-forward, the idea picked on the past does no better than the median idea: years N = 2022..2026 give -8%, 0%, -3%, +38%, +8%, against medians of -9%, +20%, +17%, +1%, 0%.
5. **Bayes 11.** A Bayesian search (Optuna TPE, 3,000 trials a year) over how votes become a book: configurations, minimum votes, number of coins, weights, exposure, cap, BTC and coin trend gates, rebalance band. Walk-forward:
   - beats the plain book in 2021 (+238% vs +129%) and in 2026 (+14.8% vs +4.0%);
   - loses in 2022 (-24% vs -16%), 2023 (+40% vs +65%) and 2024 (+13% with 60% DD vs +30%).
   - In-sample it finds +796% for 2021: textbook overfitting with 11 parameters and 6 years.
6. **Price exits, one family at a time, walk-forward.** Fixed stop, trailing stop, take profit and time stop. Sum 2021-2026: none +214%, stop +212%, take profit +215%, time stop +194%, trailing stop +108%. Tight stops cut 2020-21; none fixes 2022.
7. **16 published strategies on our data, with our costs.** None beats System 11 at equal risk in both 2025 and 2026, and none reaches its Sharpe of 1.40. The strategies:
   - crypto factors: Liu-Tsyvinski-Wu momentum and size, plus low volatility and 52-week high;
   - BTC and coin rules: Detzel MA ratio, time-series momentum, dual momentum, a Donchian ensemble;
   - others: reversal and seasonality.

   The plain "equal-weight basket while BTC > its 100-day MA" comes close: +34 a year at equal risk vs +35 for System 11, and +26% in 2026. The MLP ranking adds little on top of that gate. A vol-targeted Donchian ensemble has the best risk shape: DD 15%, Sharpe 1.16.
8. **Running now:** a robust Bayes with 4 parameters, keeping the average of the 50 best books.

## Our reading

- **The signal is real but small.** Cross-sectional IC is about 0.05 at 1 day.
- **Most of the profit is BTC regime.** It comes from being long in 2020, 2021 and 2023-24, and in cash in 2022.
- **Every layer added on top is fitted to six years.** When the choice is made walk-forward, it does not carry to the next year.
- **We may be searching the wrong space.** We are tuning rules on top of a weak ranker, instead of changing the signal, the horizon or the instrument.

## Constraints

- **Capital:** a retail book of $50k-$100k.
- **Venues:** Binance spot and USD-M perpetuals.
- **Data:** 15-minute candles from 2019 with taker volume; funding history; a lagged macro panel (FRED, Fear & Greed); point-in-time coin lists.
- **Costs:** as above.
- **Rule:** no real capital before months of forward evidence.

## What we ask

1. Why does every improvement fail walk-forward? Is our validation (nested by year, worse of two seed sets, equal-risk comparison, placebos) too strict, or is there simply nothing there?
2. Given a long-only crypto book whose returns are mostly the BTC regime, what construction would you build: trend on BTC/ETH only, a carry or funding book, market-neutral, options, or something else?
3. Which published strategies or data, with real out-of-sample evidence after 2022, should we test first, with exact parameters?
4. How would you size positions here: Kelly fraction, volatility target or regime-dependent, so that the rallies are captured without the 2022 drawdown?
5. Is "positive every year, better toward today" a reasonable target for crypto, or should we accept a down year and target long-run Sharpe?

Be specific (papers, rules, parameters) and rank by expected value vs effort.
