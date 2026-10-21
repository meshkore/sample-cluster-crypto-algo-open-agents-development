# Independent review request: crypto trading research, one page of context (round 4 - System 12)

You are an expert reviewer in quantitative finance, ML for trading and crypto. Below: the system we now run, how we got here, and its honest results. Tell us what is wrong with it, and what you would test next. Changing the problem is allowed.

## 1. How we got here

- **Systems 06-10 (Aug-Oct 2026):** 15-minute models on today's 14 liquid coins. Two external reviews found survivor bias, max-of-25,000 selection and same-bar fills; once fixed, the edge vanished.
- **System 11 (19-21 Oct):** a point-in-time top-14 coin-ranking MLP with honest execution. +30%/yr on 2020-25 (Sharpe 1.4, DD 25%), but +8% in 2025 and +1.7% in 2026. Every improvement failed walk-forward:
  - bigger size;
  - EMA and price stops;
  - 4,500 filters against a placebo;
  - Bayesian searches;
  - 16 published strategies.
- **The decisive test:** "equal-weight basket while BTC > its 100-day average" matched System 11 at equal risk. The ranking net added almost nothing; the edge was the BTC regime.

## 2. The system: System 12

- **Regime:** technical rules on BTC (50-200-day averages, 14-90-day momentum, MA-ratio rules), combined.
- **Bullish:** long BTC+ETH.
- **Bearish:** a half-size short of BTC/ETH on USD-M perpetuals.
- **Sizing:** a 40% volatility target, exposure in steps of 25%.
- **The book:** the average of 20 combinations, chosen by an exhaustive search over 75,504 (regime x basket x short x sizing).
- **Execution:** point-in-time data; decide at a 4h close, fill at the next bar; 0.10%/side plus impact; funding charged.

## 3. Results (each year traded with the 20 combinations chosen ONLY on the years before it)

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 YTD |
|---|---|---|---|---|---|---|
| System 12 | +115% | -23% | +35% | +18% | +9.7% | +5.9% |
| System 11 | +96% | -12% | +38% | +19% | +7.8% | +1.7% |
| BTC | +60% | -64% | +156% | +121% | -6% | -5% |

- **2021-2025:** +23.5%/yr, max DD 42% (2022). 2020 was chosen on 2019 alone (four months of perpetuals) and lost 49%.
- **The frozen book:** chosen on 2019-2025, it is positive in every year of that sample with DD 20%. It has been paper-traded with $50k since 2026-10-21.
- **Bigger search:** 48 signals, 14,000 configs. It did worse walk-forward (2026 -15%), so we stopped it.

## 4. Our reading and our method from here

- **The regime carries the edge.** Shorting in bear regimes is what lifted 2025-26.
- **2022 is the weak year.** The chosen rules flip too late in a crash.
- **More search finds more false winners.** From now on: one written hypothesis at a time, tested walk-forward against the frozen book, adopted only if it wins out of sample. The paper book runs untouched.

## 5. What we ask

1. Is a BTC/ETH trend book with bear-regime shorts a sound core for a $50k-$100k retail account, or are we fooling ourselves with 6 years of data?
2. How would you fix 2022: faster regime exits, volatility breaks, funding or basis signals, options?
3. Which published trend or regime methods for crypto, with real out-of-sample evidence after 2022, should we test first, with exact parameters?
4. How should the short side be sized and controlled (funding, squeezes)?
5. How long a paper record before real capital, and what would make you stop it?

Be specific (papers, rules, parameters) and rank by expected value vs effort.
