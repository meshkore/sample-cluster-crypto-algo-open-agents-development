# System 06 — results

Two eras, always labelled. A percentage without its era is not information.

- **Research / training** — 2018–2025, the years the system was allowed to be fitted on.
  These carry selection inside them and their merit is limited.
- **Sealed forward** — 2026, never optimised against, read only at adoptions, recorded
  whatever it says.

## The champion

| year | return | max drawdown | trades |
|---:|---:|---:|---:|
| 2018 | **+178.68%** | — | — |
| 2019 | +52.79% | — | — |
| 2020 | +163.11% | — | — |
| 2021 | +14,553.79% | — | — |
| 2022 | +8.68% | 11.57% | 47 |
| 2023 | +73.01% | — | — |
| 2024 | +155.72% | — | — |
| 2025 | **−2.96%** | — | — |
| **2026 SEALED** | **+25.71%** | **22.13%** | **90** |

CAGR over the research years **+205.9%**; worst research year **−2.96%**; not every year
positive (2025), which is why the consistency law remains unsatisfied.

**The mandate is +30% every calendar year. This system does not meet it** — 2022 (+8.7%)
and 2025 (−3.0%) fall short, and no filter or sizing setting has rescued them. Stating
that plainly is more useful than the headline CAGR.

## Against trivial baselines

Every arm pays the same toll — 10bp commission + 5bp slippage per side. The baselines get
no stops, no sizing and no vetoes; they also get no market impact, which makes this test
*harder* on them and therefore conservative in the champion's favour.

| year | champion | buy&hold BTC | equal-weight basket | SMA200 BTC | SMA200 basket |
|---:|---:|---:|---:|---:|---:|
| 2018 | **+178.68%** | −72.77% | −65.14% | −40.56% | −19.56% |
| 2022 | **+8.68%** | −64.40% | −67.63% | −0.33% | −33.77% |
| 2025 | −2.96% | −6.70% | **+22.07%** | −26.93% | −23.38% |
| **2026 SEALED** | **+25.71%** | −10.33% | −1.92% | +12.44% | −0.75% |

Scorecard over nine years: beats buy&hold BTC **6/9**, the basket **6/9**, SMA200-BTC
**7/9**, SMA200-basket **9/9**. CAGR +177.09% against +21.27 / +53.86 / +15.52 / +25.72%.
Worst year −2.96% against −72.77 / −67.63 / −40.56 / −33.77%.

**Where it loses is straight-line bull years** — 2019 (+53% vs BTC's +94%), 2020 (+163%
vs +302%), 2023 (+73% vs +155%) — and 2025, where the basket made +22% against its −3%.
That is the trend-follower's bargain: give up part of the upside, avoid the catastrophes.

## The sealed-reading ledger

Every reading of 2026 ever taken, win or loss. Recorded in
`research/system06/rnd/sealed_readouts.jsonl`.

| candidate | bought with | sealed 2026 | verdict |
|---|---|---|---|
| Deep-field net (RF 127) | walk-forward win +0.2019 vs +0.1643 | **−18.04%** | refused |
| Lean champion (`min_hold` 1 + 3 levers) | held-out +0.1769 vs +0.1572, ordered curve | **−11.65%** | refused |
| `min_hold` 32 | 7 of 8 walk-forward boundaries, median +0.0834 | **+22.38%** | refused |

Three for three against the incumbent's +25.71%. The diagnosis is in `SUMMARY.md` rule
2: all three were staked on edges whose year-to-year spread straddled 1.0 and which one
year therefore could not settle.

## Champion configuration

```jsonc
config: { threshold: 0.03, window: 96, epochs: 50, lr: 0.001, dropout: 0.1,
          trend_span: 5760, uniqueness_weighting: 1, ensemble: 1, embargo: 0,
          channels: [192, 192, 192] }
band:   { enter: 0.75, exit_: 0.25, min_hold: 16 }
risk:   { max_positions: 2, position_fraction: 0.15, stop_loss: 0.08, trail_stop: 0.12,
          breadth_gate: 0.30, regime_deploy: 0.50, meta_margin: 0.005,
          max_drawdown: 0.50, money_model: 0.50, fng_min: 25,
          min_notional: 100.0, max_participation: 0.10 }
```

Nine of the thirty-three levers the brain accepts are set. `max_drawdown` has never
fired; `trail_stop`, `breadth_gate` and `fng_min` were measured as carrying nothing and
remain only because their removal has never been cleanly tested on its own.

## Reading the drawdown figures

Two caveats travel with every drawdown in this file. A backtest maximum never promises
the live tail stops there. And configurations that survive only by sailing their own
limit were measured in this repository to generalise *worse* out of sample, which is why
`fast_portfolio` keeps a tighter internal line than the mandate.
