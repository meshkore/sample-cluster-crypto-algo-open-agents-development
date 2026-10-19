# Request for an independent expert review of a crypto trading research program (round 2)

You are asked to act as an independent reviewer with deep knowledge of quantitative finance, market microstructure, machine learning for trading, and crypto markets. This is round 2. After round 1, two independent reviews said our evidence did not support trading real capital, and gave us a falsification-first plan. We ran it. Below are the facts: what we built, what we tested, and every result, including the negative ones. We have deliberately left out our own view of what to do next. Reason from first principles and from the literature. We want ideas we have not considered, including changing the problem.

## 1. Goal and constraints

- Trade a real account with a system whose backtest predicts its live result. Today there is a $50,000 paper account. A live exchange mirror exists but is not armed.
- Targets: max drawdown <= 18-25%, a net return clearly above zero after realistic costs, and statistical evidence strong enough to justify capital.
- Retail-sized book ($50k-$100k). Binance spot is available, plus USD-M perpetuals for shorting.

## 2. Data and evaluation rules (from the round-1 plan)

- Binance 15-minute OHLCV with taker-buy volume, resampled to 4h and 1d for the new work.
- Research years run to 2025. 2026 is sealed, and readings of it are logged. A prospective window opened on 2026-10-19 that nothing has read.
- **Point-in-time universe only.** For year N: the top 14 USDT pairs by trailing-30-day turnover on 31 Dec of N-1, with >= 540 days of history and >= $10M/day, delisted pairs included. That is 32 coins over 2020-2025.
- **Execution:**
  - decide at the close of t, fill at the close of t+1;
  - 0.45% round trip, plus square-root impact (sigma_daily x sqrt(order / ADV), $100k book; 0.01% per side on BTC, up to 0.4% on the 14th pair);
  - stops checked intrabar against the bar's low and high, worst case;
  - perpetual funding charged on shorts.
- **Walk-forward:** models train on years < N, with a label-end embargo (no label reads a price of N).
- **Nested selection:** a configuration is chosen on years < N only, then N is read.
- **Statistics:** every metric gets a 10-day block-bootstrap CI, on two independent seed sets, keeping the worse.

## 3. The original system (round 1) and what happened to it

The original system ran per 15-minute bar on each coin:
- a market gate (BTC vs its 100-day average, plus breadth);
- 4 small MLPs selecting entries (target: net return minus max adverse excursion);
- 4 MLPs forecasting the next 24h return, which drove the exit;
- a rule book: 5 slots, a 12% stop, x2 stake on momentum leaders, drawdown scaling.

About 25,000 configurations were searched, and the top one by score was released.

| test | result |
|---|---|
| Phase 0: execution | Nested PIT return 2023-2025, compounded, on the two seed sets: +25% / +59% at base execution, -9% / -15% with all frictions. Break-even cost is a 0.6-0.8% round trip. Filling one bar later moves single years by up to 30 points either way. |
| Phase 1: alpha vs beta | Alpha against an equal-weight PIT basket: t < 2 on every series (best 1.41). No Sharpe gain over a naive rule (equal weight when BTC > MA100). Beta about 0.1: mostly cash. |
| Overfitting | PBO 0.76 on PIT. Seed noise: the same configuration with other seeds moves a year by a median of 7.7 points. |

Verdict: retired as a capital candidate.

## 4. The new pipeline (round-1 plan, phases 3-4)

- **Space:** 72 configurations. Five levers: timeframe (4h / 1d), horizon (1 / 3 / 7 days), number of holdings K (3 / 5 / 8), a BTC-regime gate (on / off), and the model (ridge / gradient boosting).
- **Target:** one model of the expected net return of an entry, cost included.
- **Features:** 28 causal ones: returns 1-90 days, volatility, distance to 20 / 50 / 100-day averages, RSI, dollar-volume z-score, taker share, range, BTC returns and regime, breadth, market return, and cross-sectional ranks.
- **Book:** hold the top K with a positive prediction for H, with hysteresis.
- **Phase 4 risk layer:**
  - each position carries 1% daily risk (inverse volatility);
  - book volatility <= 2% a day from the 90-day covariance;
  - correlation clusters (rho > 0.85) capped at 40%;
  - no leverage.
- **Selection:** nested. Score = p5 of the bootstrap Sharpe. DD <= 18% is a constraint. Argmax vs bagging the top 10 / 20.

| test | result |
|---|---|
| Long-only, phase 3 | Medians over configurations, 2022 / 2023 / 2024 / 2025: -35 / +47 / +22 / -16% net. Turnover 34-71x a year. No configuration has DD <= 18% in 2021 or 2022, so nested selection holds cash. Seed noise 8.5 points. |
| Risk layer, phase 4 | Median tail DD 59% -> 43%; median net 2022-2025 -4% -> +13%; seed noise 5.1 points. Nested, bagging top 10: -13.6% (seed set 1), +92% (seed set 2: one surviving configuration). |
| Long/short, phase 3b | Long top K, short bottom K, dollar neutral, perpetuals for shorts. Wins 2022 and 2025, loses the 2023-2024 rallies (low-ranked coins squeezed). Nested Sharpe -0.06 (worse seed set) and 0.57. |
| The signal itself | Cross-sectional Spearman IC of predictions vs GROSS forward return, out of sample: 0.02-0.15, t > 2 in most years at 4h, weak at 1d. A first measurement against NET return showed about twice that. That was an artefact: the target subtracts each coin's cost, which the features can predict. |
| Sealed 2026, one reading, frozen models | Only the 4h / 1-day horizon survives: gross IC 0.05-0.06, t 2.5-2.8. Top-3 minus bottom-3 gross spread: about 0 a day. |

**Forward-test arithmetic.** Showing at 2 sigma that a Sharpe S is above zero needs about (2 x sqrt(365) / S)^2 days: S 1.0 needs 4 years, S 0.8 about 6. Our best honest Sharpe is 0.8 on one seed set.

## 5. Experiments closed earlier (do not re-propose without a new reason)

- About 40,000 filter and sizing add-ons on the original model, each with a placebo: moving averages 1-300, RSI, MACD, ~17 indicator families, macro, funding, sentiment, calendar, and combinations. Also martingale, anti-martingale, conviction sizing, and rule mining plus gradient boosting over 76 entry features. Real ideas did no better than placebos (1.5% vs 3.3% improve).
- Reinforcement-learning agents: they stopped trading or memorised the path.
- A bar-by-bar learned exit: lost money to costs.
- Earlier lines: perfect-hindsight oracle labels with a neural net, a cross-sectional ranking model, and a fixed-target system. None held out of sample.

## 6. What we ask you

Do not assume our market, horizon, target, universe or book is right.

1. Given a real but small cross-sectional signal (gross IC about 0.05 at 1 day, weaker at longer horizons) and a 0.45-1% round trip, is there any construction that can monetise it at retail size? If not, say so.
2. Which assumptions would you change first? Consider asset class, venue and fee tier, holding period, universe breadth, prediction target, long/short construction, and execution style (maker vs taker).
3. Name data sources or signals with published out-of-sample evidence in crypto that we have not tried (see section 5), and say how to test each one honestly in our setting.
4. Is our validation too strict, too lenient, or wrong anywhere?
5. With a forward test that needs years to confirm a Sharpe near 1, what is a rational path to real capital, or a rational decision to stop?

Be specific (papers, methods, parameters), rank proposals by expected value vs effort, and disagree with us where the evidence supports it.
