# System 12 - BTC regime core, walk-forward

13,552 configurations (484 regimes x 7 baskets x 4 sizings). Each year is read with what was chosen on the years before it. Costs charged. Each year from the same capital.

| year | chosen on | single best (its rule) | average of the 20 best | median of all configs |
|---|---|---|---|---|
| 2020 | 2019-2019 | +87.3% <small>BTC>MA100 AND breadth >100d avg > half / BTC / 0.0</small> | +90.6% (DD 40%) | +83.7% |
| 2021 | 2019-2020 | +152.7% <small>BTC 14d momentum AND BTC>MA50 / BTC+ETH / 0.0</small> | +107.2% (DD 20%) | +98.5% |
| 2022 | 2019-2021 | -30.1% <small>BTC>MA50 AND breadth >50d avg > half / 5 strongest (90d) / 0.0</small> | -26.0% (DD 30%) | -17.5% |
| 2023 | 2019-2022 | +37.4% <small>BTC>MA100 AND breadth >50d avg > half / equal weight / 0.0</small> | +45.0% (DD 26%) | +29.9% |
| 2024 | 2019-2023 | +43.0% <small>BTC Donchian 55d AND BTC>MA100 / inverse volatility / 0.0</small> | +40.4% (DD 34%) | +36.9% |
| 2025 | 2019-2024 | -4.8% <small>BTC 14d momentum AND BTC>MA150 / BTC / 0.6</small> | -5.3% (DD 19%) | -11.8% |
| 2026 (forward) | 2019-2025 | -3.2% <small>BTC 60d momentum AND BTC>MA100 / BTC+ETH / 0.4</small> | +0.7% (DD 9%) | +5.8% |

Reference (no selection):

| | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| System 11 (paper scale) | - | +59% | +96% | -12% | +38% | +19% | +8% | +1.5% |
| BTC buy & hold | +94% | +302% | +60% | -64% | +156% | +121% | -6% | -5% |
| equal-weight basket, always | +15% | +209% | +307% | -58% | +96% | +57% | -41% | -4% |
| equal weight while BTC > MA100 | +14% | +93% | +673% | -23% | +53% | +25% | -21% | +26% |

The 20 configurations chosen on 2019-2025 (System 12 for 2026):

- BTC 60d momentum AND BTC>MA100 / BTC+ETH / 0.4
- BTC 60d momentum AND BTC>MA150 / BTC+ETH / 0.4
- BTC>MA100 AND BTC>MA50 / BTC+ETH / 0.4
- BTC>MA100 AND BTC>MA150 / BTC+ETH / 0.4
- BTC>MA150 AND BTC>MA50 / BTC+ETH / 0.4
- BTC 60d momentum AND BTC MA-ratio rules (Detzel) / BTC+ETH / 0.4
- BTC 90d momentum AND BTC>MA200 / BTC+ETH / 0.4
- BTC 90d momentum AND BTC>MA150 / BTC+ETH / 0.4
- BTC>MA100 / BTC+ETH / 0.4
- BTC 14d momentum AND BTC>MA150 / BTC+ETH / 0.6
- mean(BTC MA ensemble 20/50/100/200 | BTC>MA100) / BTC+ETH / 0.4
- BTC 90d momentum AND BTC MA-ratio rules (Detzel) / BTC+ETH / 0.4
- BTC 60d momentum AND BTC>MA200 / BTC+ETH / 0.4
- mean(BTC 30d momentum | BTC MA ensemble 20/50/100/200) / BTC+ETH / 0.4
- BTC 14d momentum AND BTC 30d momentum / BTC+ETH / 0.4
- BTC MA-ratio rules (Detzel) AND BTC>MA150 / BTC+ETH / 0.4
- BTC 14d momentum AND BTC>MA100 / BTC+ETH / 0.4
- BTC 14d momentum AND BTC>MA150 / BTC+ETH / 0.4
- mean(BTC MA-ratio rules (Detzel) | BTC>MA150) / BTC+ETH / 0.4
- BTC MA-ratio rules (Detzel) AND BTC>MA200 / BTC+ETH / 0.4
