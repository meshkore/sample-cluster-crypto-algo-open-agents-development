# Request for an independent expert review of a crypto trading research program

You are asked to act as an independent reviewer with deep knowledge of quantitative finance, market microstructure, machine learning for trading, and crypto markets. Below is a factual description of what we built, how it was trained and validated, and the results we measure. We have deliberately left out our own views on what to do next, so as not to steer you. Reason from first principles and from the literature. We want ideas we have not considered, including changing the problem itself.

## 1. Goal and constraints

- Trade a real account (now a $50,000 paper account; a live exchange mirror exists but is not armed) with a system whose backtest predicts its live result.
- Targets we set: positive return in every calendar year, max drawdown <= 25%, able to trade on >= 70% of days (no gap > 40 days), >= 50 trades per year.
- Today: crypto spot, USDT pairs, long only, 15-minute bars.

## 2. Data

- Binance spot 15-minute OHLCV (including taker-buy volume), 2019/2020 to October 2026. Research years are <= 2025. 2026 (January to mid-October) is never used for fitting or selection, only read afterwards as a forward check.
- Two coin universes:
  - "Today's 14": the 14 most liquid pairs as of 2026. This list is survivor-selected.
  - "Point-in-time" (PIT): for test year N, the top 14 pairs by trailing-30-day turnover on 31 Dec of N-1, with >= 540 days of history and >= $10M/day, delisted pairs included. That is 32 distinct coins over 2020-2026.
- Also available: a lagged macro panel (VIX, Nasdaq-100, dollar index, oil, US 10-year yield, yield curve), Crypto Fear & Greed, perpetual funding rates, open interest, and calendar fields.
- Costs: 0.30% round trip per trade, filled at the 15-minute close.

## 3. The current system, per coin and per 15-minute bar

1. **Market gate.** The regime is set by BTC against its 100-day moving average and by market breadth (share of coins above their own average). In the up regime it trades when breadth is >= 0.5. In the down regime it is open at 0.75x stake.
2. **Selector.** There is one set of models per regime: 4 small neural nets (MLP 2x128, Huber loss, 6 epochs, different seeds).
   - Training rows: every gated bar of past years.
   - Target: (net return minus maximum adverse excursion) of a trade entered at that bar under a fixed exit (stop, trail, max hold).
   - Inputs: 44 price and volume features per coin, plus 1h, 4h, 1d and 1w views, plus the lagged macro panel.
   - A bar is taken when >= 3 of the 4 nets score above a bar. The bar is a "take share" between 10% and 50% of bars, chosen on the previous year (or per regime).
3. **Exit and forecast model.** 4 MLPs regress the next 96-bar (24-hour) return, clipped at +-30%. It enters if the forecast is > +0.3% and holds while it is > -0.3%. The stake grows with forecast strength.
4. **Book (money management), deterministic rules:**
   - 5 slots;
   - stake = slot x forecast strength x 0.75 in the down regime x drawdown scaling x 2 for the top-7 coins by 90-day return;
   - scale in or out every 4 hours;
   - per-trade stop 12%, breakeven move at +8%, take profit 20%, max hold 768 bars (8 days);
   - at most 3 highly correlated coins held at once;
   - an equity-curve filter.

**Walk-forward.** For test year N: the selector is fitted on years <= N-2, its take share is chosen on N-1, the exit model is fitted on years < N, and N is read. No model sees the year it is scored on.

## 4. How a configuration is chosen

- An automatic search walks about 40 discrete design choices: gate average, breadth thresholds, feature sets, hold horizon, take share, and sizing and risk levers.
- About 23,600 configurations were evaluated on today's 14 (2022-2025). About 1,500 were evaluated on PIT, each on two independent seed sets, keeping the weaker result.
- Score = 0.5 x worst-year return + 0.5 x recency-weighted return - 0.25 x max drawdown, plus the hard rules in section 1. The top configuration becomes a "release" and runs on the paper account.
- Controls in place:
  - Probability of Backtest Overfitting (PBO, CSCV over the trial ledger);
  - the Deflated Sharpe ratio;
  - a nested selection: the configuration is chosen on years < N, then N is read;
  - a measured seed-noise band;
  - a release gate that refuses PBO > 0.5, any nested year <= 0, or an eligible pool under 20.

## 5. Results

**A. Current paper release, chosen on today's 14, backtest 2022-2025:**

| year | return | max DD | trades | win rate |
|---|---|---|---|---|
| 2022 | +32.7% | 16.6% | 322 | 54% |
| 2023 | +17.8% | 4.8% | 83 | 73% |
| 2024 | +93.0% | 21.8% | 1,697 | 59% |
| 2025 | +26.1% | 24.9% | 1,455 | 50% |

**B. Earlier releases re-run on the honest PIT coin list**, as returns for 2022 / 2023 / 2024 / 2025 / 2026 to date:

| release | today's 14 | PIT |
|---|---|---|
| A | +43 / +19 / +80 / +35 / +40 | 0 (no trades) / +9 / +12 / +64 / -15, max DD 32% |
| B | +9 / +16 / +106 / +80 / +49 | 0 (no trades) / +11 / +36 / +98 / -6 |

**C. The selection itself walk-forward (nested)**, as returns for 2023 / 2024 / 2025:

| list and seed set | returns | max DD |
|---|---|---|
| today's 14, seed set 1 | +21 / +40 / +22 | 26% |
| today's 14, seed set 2 | +10 / +9 / +16 | 26% |
| PIT, seed set 1 | +20 / -0.1 / +5 | 27% |
| PIT, seed set 2 | +25 / +14 / +12 | 21% |

**D. Other measurements:**
- PBO is 0.57 on today's 14 and 0.76 on PIT. The Deflated Sharpe probability is 0.87 and 0.95 (monthly, 48 months).
- Best PIT configuration, in-sample, 2022 / 2023 / 2024 / 2025: +13 / +15 / +33 / +55% on seed set 1 and +16 / +24 / +22 / +57% on seed set 2, max DD <= 22%.
- Noise: re-running the same configuration with another seed set moves one year's return by a median of 7.7 points (90th percentile 30 points). The top 100 configurations differ by less than 0.023 of score.
- Forward paper account since 2026-10-13: 4 closed trades, -0.02%. Too short to judge.
- Status: no configuration has yet passed the release gate on the PIT universe.

## 6. Parallel experiment "Rocket": filters and sizing on top of the frozen model

We froze the current model's signals and tested about 33,000 add-ons. Each add-on was chosen on years < N and read on N, run on both universes, and compared against a placebo: the same procedure on time-shifted or shuffled data.

- **Trade vetoes and filters:**
  - moving averages of 1-300 periods on 15m to 1w;
  - RSI, MACD, crosses, and about 17 other indicator families;
  - BTC-relative, market-relative and rank-relative versions;
  - macro, funding, Fear & Greed, calendar and model-output conditions;
  - pairs and triples of the above.
- **Position sizing:**
  - martingale (size up after losses) and anti-martingale (after wins), with caps and drawdown gates;
  - conviction multipliers from indicator agreement;
  - a "miner": rule mining over 76 entry-time features, plus gradient boosting, that sizes up when conditions that won in the past hold again.
- **Result:** the share of real add-ons that improve the score is at or below the placebo share: 1.5% vs 3.3% on today's 14, and 0.7% vs 1.0% on PIT. Conditions the miner finds win 60-73% of trades in training vs 40-55% outside them. In the following year that gap disappears or reverses.

## 7. Tried earlier and closed

- Reinforcement-learning agents (long/flat/short, same data). They either learned to stop trading or memorised the training path, and results swung widely between retrainings.
- A bar-by-bar learned exit lost money to costs.
- Earlier lines failed to hold consistently in held-out years:
  - perfect-hindsight "oracle" labels with a neural net on 15-minute BTC and multi-coin data;
  - a cross-sectional ranking model;
  - a fixed-target system.

## 8. What we ask you

Do not assume our architecture, target or market is right.

1. From these numbers alone: is there evidence of a tradeable edge, and how strong is it? What do the PIT and nested results tell you?
2. Which assumptions would you change first, and why? Consider asset class, horizon, long only, universe, prediction target, cost model, and the evaluation method.
3. Give concrete approaches from the literature or from practice that are not listed above. For each, say why it should work in this setting, how to test it honestly, and what result would falsify it.
4. How would you design forward testing and the path to live capital, so that money is committed only with quantified confidence? Include sample size, duration, and stop rules.
5. Do you see any flaw in our validation: leakage, selection bias, or a cost or fill model that is too optimistic?

Be specific (papers, methods, parameters), rank your proposals by expected value vs effort, and disagree with us where the evidence supports it.
