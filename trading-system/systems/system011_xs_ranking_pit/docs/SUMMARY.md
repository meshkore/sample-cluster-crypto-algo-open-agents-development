# System 11 - cross-sectional coin ranking on point-in-time lists (CLOSED 2026-10-21)

Code and runs: `research/plan_v2/` (see `ARCHIVED.md` there). Successor: System 12 (`system012_btc_regime`).
The external review request (rounds 2-3) written about this system: `research/architecture_brief/brief_round3_system11.md`.

## 1. Hypothesis

A model trained only on the past can rank the most-traded coins against each other well enough to beat holding them all. Holding the top few, out of sample and after honest costs, earns more than the market with a controlled drawdown.

## 2. What it is

- **Universe:** the point-in-time top-14 coins by turnover on 31 Dec of the year before, delisted coins included; Binance spot, long only.
- **Model:** small neural nets (MLP) on 28 causal features at 4h and 1d. The target is each coin's rank over the next 1/3/7 days.
- **Configurations:** 36 (timeframe x horizon x hold the top 3/5/8). For year N the 10 best on earlier years are averaged.
- **Gate and sizing:** BTC > 100-day average; exposure scaled to an 18% drawdown budget.
- **Execution:** fills at the next bar, 0.225%/side plus square-root impact; two seed sets, keeping the worse.
- **History:** models trained on years < N only, from 2018. 2026 is the forward test.

## 3. What helped

| change | measured effect | evidence |
|---|---|---|
| Point-in-time universe, honest execution (fill t+1, impact) | removed the survivor and same-bar biases that made Systems 06-10 look good | phase 0 falsified the old numbers (+25%/+59% -> -9%/-15%) |
| Cross-sectional ranking target, MLP | nested Sharpe +0.64, positive on 100% of 100 seed pairs | lab, 1,260+ experiments |
| Selection by "positive every past year, better toward today" (grid C law) | Sharpe 0.75 vs 0.64; fixed 2025 (+18% vs 0%) | 45 seed pairs |
| Exposure scaled to the DD budget | 2020-25 max DD 25%, +30%/yr, Sharpe 1.40 | full-history walk-forward |

## 4. What hurt

| change | measured effect | evidence |
|---|---|---|
| Bigger positions (2x-4x) | only the 2020-21 bull years improved; 2024 DD 54%, 2025 negative | same signals, 0.45x to 4x |
| Sell below EMA 20/50 | +25% vs +30%/yr | `ema_exit_test.py` |
| Price exits: fixed stop, trailing stop, take profit, time stop | sum 2021-26: +212% / +108% / +215% / +194% vs +214% | `exits11/`, walk-forward |
| 4,500 filter and sizing ideas (Rocket 11) | the walk-forward pick was no better than the median idea | `rocket11/`, placebo-controlled |
| Bayesian search over 11 levers (Bayes 11) | won 3 of 6 years walk-forward; 2024 DD 60%; in-sample +796% | `bayes11/` |
| Robust Bayes (4 levers, top-50 consensus) | 2026 +3.2% vs +4.2% plain | `bayes11_robust/` |
| Recency-weighted training, faster bear exit | no gain | grid C |
| Long/short ranking (phase 3b) | wins 2022 and 2025, loses the 2023-24 rallies | `PHASE3B.md` |

## 5. What is still open

- **Does the ranking add anything beyond the BTC gate?** At equal risk, "all coins, equal weight, while BTC > MA100" earned +34%/yr vs +35%. Untested: a ranking inside System 12's regime.
- **Wider universe (top 20/30).** Tried in the lab with no clear gain; not settled.

## 6. Rules learned

- The edge here was the BTC regime, not the coin ranking. Always compare a model with "the plain basket under the same gate" at equal risk.
- More search produces more in-sample winners that fail walk-forward. Judge any search by the year AFTER the choice, never by its best result.
- A trade list can look excellent while the book earns little: positions of 1-8% of capital turn +20% coin moves into +5% for the book.
- Size pays only in bull years. Since 2023 it added drawdown, not return.
- 2026 is read, never used to choose.
