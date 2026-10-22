# Task 11 - the net-liquidity filter in 2014-2020 (years the system never saw)

Spot BTC, long only, 40% volatility target, 0.10%/side, decided at the close. 2014-2020 is the new evidence; 2021-2026 is shown for reference (the spx row exists only from 2017).

| strategy | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | DD 2014-20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC buy and hold | -56% | +34% | +126% | +1337% | -74% | +94% | +305% | +60% | -64% | +155% | +121% | -6% | -4% | 84% |
| trend rule (60d mom & > MA100) | -3% | +8% | +70% | +268% | -15% | +103% | +85% | +34% | -13% | +70% | +71% | +5% | +11% | 36% |
| + liquidity filter (nasdaq, n=126, lo=0.0, hi=1.0) <- pre-registered | -8% | -23% | -13% | -4% | +0% | +5% | +71% | +40% | -2% | +100% | -6% | +23% | +17% | 52% |
| + liquidity filter (spx, n=126, lo=0.0, hi=1.0) | +0% | +0% | +0% | -9% | +0% | +5% | +61% | +66% | +3% | +130% | -2% | +22% | +16% | 26% |
| + liquidity filter (nasdaq, n=126, lo=0.0, hi=1.5) | -1% | -11% | +9% | +11% | +0% | +22% | +86% | +50% | -8% | +76% | +46% | +24% | +17% | 39% |
| + liquidity filter (nasdaq, n=126, lo=0.5, hi=1.0) | -7% | -31% | -3% | +19% | +0% | -2% | +53% | +34% | -8% | +101% | -2% | +27% | +11% | 50% |
| + liquidity filter (nasdaq, n=126, lo=0.5, hi=1.5) | -1% | -16% | +20% | +20% | +0% | +26% | +66% | +40% | -13% | +77% | +45% | +34% | +8% | 42% |
| + liquidity filter (nasdaq, n=252, lo=0.0, hi=1.0) | -1% | +8% | -3% | +1% | +0% | +0% | +1% | +34% | -6% | +92% | -4% | +8% | +4% | 30% |
| + liquidity filter (nasdaq, n=252, lo=0.0, hi=1.5) | -2% | +13% | +19% | +12% | +0% | +0% | +32% | +34% | -13% | +99% | +8% | +9% | +4% | 26% |
| + liquidity filter (nasdaq, n=252, lo=0.5, hi=1.0) | -2% | +11% | +20% | -6% | +0% | -7% | +33% | +59% | -12% | +83% | -4% | +8% | +12% | 40% |
| + liquidity filter (nasdaq, n=252, lo=0.5, hi=1.5) | +0% | +14% | +29% | -2% | +0% | -5% | +105% | +34% | -13% | +96% | +6% | +9% | +12% | 28% |

Pre-registered filter vs the plain trend rule, 2014-2020: better in 1 years, worse in 6.
