# Classics 11 - published crypto strategies on System 11's data

Generated 2026-10-21T12:49:30+00:00. Script: `research/plan_v2/classics11.py`. Long-only spot, PIT top-N members, 0.225%/side + ADV impact, signals read at the last daily close before each 4h decision. Each year from the same capital. DD and Sharpe on 2020-2025. **EqR** = the 2020-2025 average yearly return after rescaling the daily series to a 25% max DD (System 11 paper scale; k>1 is a comparison only, a spot book cannot lever). 2026 (to date) is forward: never used to choose. Walk-forward lines choose their parameter for year N on 2019..N-1.

## Top-14 universe

| strategy | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | DD | Sharpe | expo | k | EqR avg | EqR 2025 | EqR 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| System 11 (paper scale, reference) | +59 | +96 | -12 | +38 | +19 | +8 | +2 | 25 | 1.40 | - | 1 | +35 | +8 | +1.5 |
| System 11 law book (unscaled, reference) | +89 | +129 | -16 | +66 | +30 | +2 | +4 | 39 | - | - | - | - | - | - |
| BTC buy & hold | +302 | +60 | -64 | +156 | +121 | -6 | -5 | 77 | 0.99 | 1.00 | 0.23 | +16 | +0 | +0.3 |
| EW basket of members | +209 | +307 | -58 | +96 | +57 | -41 | -4 | 80 | 0.88 | 1.00 | 0.22 | +17 | -7 | +1.4 |
| EW basket when BTC > MA100 | +93 | +673 | -23 | +53 | +25 | -21 | +26 | 53 | 1.12 | 0.61 | 0.40 | +34 | -6 | +10.9 |
| XS momentum (top third, 3-week) | +247 | +284 | -65 | +152 | +68 | -35 | -40 | 89 | 0.94 | 1.00 | 0.18 | +15 | -4 | -6.9 |
| XS momentum (top third, 3-week) [walk-forward] | +274 | +286 | -66 | +87 | +68 | -35 | -40 | 88 | 0.89 | 1.00 | 0.17 | +14 | -4 | -6.7 |
| XS size (small third, turnover proxy) | +255 | +539 | -43 | +36 | +37 | -55 | -7 | 82 | 0.90 | 0.99 | 0.22 | +20 | -12 | +0.9 |
| XS size (small third, turnover proxy) [walk-forward] | +255 | +539 | -43 | +36 | +37 | -55 | -7 | 82 | 0.90 | 0.99 | 0.22 | +20 | -12 | +0.9 |
| BTC TS momentum (1-week) | +140 | +50 | -43 | +50 | +32 | -9 | -6 | 60 | 0.71 | 0.54 | 0.34 | +11 | -2 | -1.5 |
| BTC TS momentum (1-week) [walk-forward] | +359 | -17 | -25 | +150 | +71 | +2 | -8 | 64 | 1.18 | 0.54 | 0.31 | +19 | +1 | -1.9 |
| BTC MA-ratio rules (5-100d ensemble) | +185 | +67 | -48 | +70 | +61 | -11 | -0 | 62 | 0.97 | 0.55 | 0.31 | +13 | -3 | +0.3 |
| BTC MA-ratio rules (5-100d ensemble) [walk-forward] | +154 | +119 | -50 | +80 | +69 | -1 | +12 | 59 | 1.03 | 0.60 | 0.33 | +17 | +0 | +4.2 |
| XS short-term reversal (1-day) | -63 | -85 | -93 | -65 | -78 | -89 | -69 | 100 | -1.60 | 1.00 | 0.03 | -4 | -6 | -3.3 |
| XS short-term reversal (1-day) [walk-forward] | -25 | -21 | -81 | -32 | -19 | -71 | -54 | 99 | -0.37 | 1.00 | 0.08 | -3 | -7 | -5.0 |
| XS low volatility (30d) | +316 | +161 | -61 | +88 | +95 | -10 | -6 | 80 | 0.99 | 1.00 | 0.22 | +17 | -0 | -0.1 |
| XS low volatility (30d) [walk-forward] | +314 | +318 | -49 | +98 | +126 | -18 | -19 | 71 | 1.20 | 1.00 | 0.28 | +26 | -3 | -4.3 |
| XS high idiosyncratic vol (30d) | +41 | +112 | -76 | +83 | +54 | -61 | -11 | 95 | 0.42 | 1.00 | 0.13 | +5 | -8 | +0.9 |
| XS high idiosyncratic vol (30d) [walk-forward] | +56 | +48 | -76 | +83 | +54 | -61 | -11 | 94 | 0.37 | 1.00 | 0.15 | +5 | -9 | +0.9 |
| XS illiquidity (Amihud 30d) | +140 | +373 | -60 | +64 | +8 | -65 | -8 | 87 | 0.65 | 0.99 | 0.19 | +12 | -14 | +1.2 |
| XS illiquidity (Amihud 30d) [walk-forward] | +148 | +333 | -63 | +51 | -2 | -65 | -11 | 90 | 0.60 | 0.99 | 0.20 | +12 | -14 | +0.5 |
| Dual momentum BTC/ETH (12m) | +164 | +399 | -25 | +38 | +121 | -8 | -5 | 57 | 1.18 | 0.78 | 0.40 | +38 | -1 | -1.6 |
| Dual momentum BTC/ETH (12m) [walk-forward] | +108 | +144 | -39 | +38 | +121 | -8 | -5 | 69 | 0.90 | 0.74 | 0.30 | +18 | -1 | -1.2 |
| Vol-scaled TSMOM (12m, 40% vol) | +21 | +74 | -8 | +19 | +33 | -12 | +0 | 27 | 0.80 | 0.29 | 0.92 | +20 | -11 | +0.4 |
| Vol-scaled TSMOM (1/3/12m blend) | +10 | +56 | -2 | +16 | +4 | -5 | +1 | 19 | 0.71 | 0.17 | 1.32 | +17 | -7 | +1.4 |
| Per-coin MA trend (20/50/100/200 ensemble) | +97 | +238 | -36 | +30 | +40 | -26 | +3 | 68 | 0.86 | 0.51 | 0.29 | +13 | -7 | +1.4 |
| Per-coin MA trend (20/50/100/200 ensemble) [walk-forward] | +48 | +232 | -38 | +44 | +30 | -36 | +2 | 57 | 0.70 | 0.51 | 0.38 | +15 | -14 | +1.7 |
| Donchian ensemble, vol-targeted | +27 | +25 | -6 | +10 | +13 | -2 | +0 | 15 | 1.16 | 0.10 | 1.69 | +20 | -4 | +0.4 |
| XS nearness to 52-week high | +317 | +593 | -66 | +136 | +85 | -35 | +0 | 83 | 1.13 | 1.00 | 0.22 | +22 | -6 | +1.5 |
| XS nearness to 52-week high [walk-forward] | +280 | +621 | -69 | +95 | +108 | -27 | -18 | 84 | 1.10 | 1.00 | 0.20 | +20 | -4 | -2.7 |
| BTC-dominance rotation (30d) | +161 | +253 | -67 | +68 | +82 | -7 | -29 | 83 | 0.87 | 1.00 | 0.19 | +14 | +1 | -4.8 |
| BTC-dominance rotation (30d) [walk-forward] | +159 | +206 | -61 | +140 | +87 | -43 | -23 | 84 | 0.84 | 1.00 | 0.21 | +15 | -9 | -3.7 |
| BTC Monday effect | +44 | -27 | -25 | -18 | +22 | -24 | +7 | 64 | -0.16 | 0.14 | 0.30 | -1 | -7 | +2.3 |
| BTC turn of month | -7 | +47 | -12 | -5 | -30 | +10 | -10 | 51 | -0.01 | 0.13 | 0.42 | +0 | +4 | -4.1 |

Beat System 11 at equal risk (2020-25 avg > +35%): Dual momentum BTC/ETH (12m)
Beat System 11 in 2025 at equal risk (> +8%): none
Beat System 11 in 2026 YTD at equal risk (> +1.5%): EW basket when BTC > MA100, BTC MA-ratio rules (5-100d ensemble) [walk-forward], Per-coin MA trend (20/50/100/200 ensemble) [walk-forward], XS nearness to 52-week high, BTC Monday effect
All three: none

## Top-20 universe

| strategy | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | DD | Sharpe | expo | k | EqR avg | EqR 2025 | EqR 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| System 11 (paper scale, reference) | +59 | +96 | -12 | +38 | +19 | +8 | +2 | 25 | 1.40 | - | 1 | +35 | +8 | +1.5 |
| System 11 law book (unscaled, reference) | +89 | +129 | -16 | +66 | +30 | +2 | +4 | 39 | - | - | - | - | - | - |
| BTC buy & hold | +302 | +60 | -64 | +156 | +121 | -6 | -5 | 77 | 0.99 | 1.00 | 0.23 | +16 | +0 | +0.3 |
| EW basket of members | +209 | +296 | -65 | +93 | +41 | -44 | +5 | 82 | 0.80 | 1.00 | 0.22 | +16 | -8 | +3.3 |
| EW basket when BTC > MA100 | +93 | +704 | -22 | +56 | +8 | -25 | +44 | 57 | 1.07 | 0.61 | 0.37 | +30 | -7 | +15.4 |
| XS momentum (top third, 3-week) | +247 | +259 | -67 | +88 | -2 | -42 | -20 | 88 | 0.73 | 1.00 | 0.20 | +13 | -7 | -1.9 |
| XS momentum (top third, 3-week) [walk-forward] | +274 | +149 | -67 | +88 | -2 | -42 | -20 | 88 | 0.67 | 1.00 | 0.20 | +12 | -7 | -1.9 |
| XS size (small third, turnover proxy) | +255 | +288 | -76 | +53 | +51 | -58 | -12 | 90 | 0.68 | 0.99 | 0.19 | +13 | -11 | -0.2 |
| XS size (small third, turnover proxy) [walk-forward] | +255 | +288 | -76 | +54 | +36 | -58 | -12 | 90 | 0.66 | 0.99 | 0.19 | +13 | -11 | -0.2 |
| BTC TS momentum (1-week) | +140 | +50 | -43 | +50 | +32 | -9 | -6 | 60 | 0.71 | 0.54 | 0.34 | +11 | -2 | -1.5 |
| BTC TS momentum (1-week) [walk-forward] | +359 | -17 | -25 | +150 | +71 | +2 | -8 | 64 | 1.18 | 0.54 | 0.31 | +19 | +1 | -1.9 |
| BTC MA-ratio rules (5-100d ensemble) | +185 | +67 | -48 | +70 | +61 | -11 | -0 | 62 | 0.97 | 0.55 | 0.31 | +13 | -3 | +0.3 |
| BTC MA-ratio rules (5-100d ensemble) [walk-forward] | +154 | +119 | -50 | +80 | +69 | -1 | +12 | 59 | 1.03 | 0.60 | 0.33 | +17 | +0 | +4.2 |
| XS short-term reversal (1-day) | -63 | -83 | -96 | -74 | -87 | -92 | -76 | 100 | -1.87 | 1.00 | 0.03 | -4 | -6 | -3.5 |
| XS short-term reversal (1-day) [walk-forward] | -25 | -18 | -85 | -26 | -43 | -74 | -58 | 100 | -0.44 | 1.00 | 0.07 | -3 | -7 | -5.2 |
| XS low volatility (30d) | +316 | +255 | -63 | +79 | +91 | -4 | -5 | 78 | 1.05 | 1.00 | 0.22 | +18 | +2 | +0.1 |
| XS low volatility (30d) [walk-forward] | +314 | +391 | -51 | +104 | +111 | -12 | -14 | 70 | 1.22 | 1.00 | 0.27 | +27 | -0 | -2.5 |
| XS high idiosyncratic vol (30d) | +41 | +149 | -72 | +50 | +7 | -63 | +47 | 94 | 0.38 | 1.00 | 0.17 | +6 | -11 | +9.9 |
| XS high idiosyncratic vol (30d) [walk-forward] | +56 | +117 | -82 | +49 | +7 | -63 | +47 | 95 | 0.29 | 1.00 | 0.15 | +4 | -9 | +8.7 |
| XS illiquidity (Amihud 30d) | +140 | +391 | -74 | +53 | +11 | -62 | -6 | 91 | 0.60 | 0.99 | 0.20 | +13 | -13 | +1.5 |
| XS illiquidity (Amihud 30d) [walk-forward] | +148 | +292 | -77 | +53 | +11 | -62 | -6 | 93 | 0.54 | 0.99 | 0.18 | +10 | -12 | +1.5 |
| Dual momentum BTC/ETH (12m) | +164 | +399 | -25 | +38 | +121 | -8 | -5 | 57 | 1.18 | 0.78 | 0.40 | +38 | -1 | -1.6 |
| Dual momentum BTC/ETH (12m) [walk-forward] | +108 | +144 | -39 | +38 | +121 | -8 | -5 | 69 | 0.90 | 0.74 | 0.30 | +18 | -1 | -1.2 |
| Vol-scaled TSMOM (12m, 40% vol) | +21 | +74 | -6 | +17 | +26 | -12 | -0 | 27 | 0.77 | 0.27 | 0.92 | +18 | -11 | -0.3 |
| Vol-scaled TSMOM (1/3/12m blend) | +10 | +57 | -2 | +15 | +2 | -6 | +1 | 20 | 0.69 | 0.16 | 1.29 | +17 | -9 | +0.9 |
| Per-coin MA trend (20/50/100/200 ensemble) | +97 | +221 | -37 | +33 | +19 | -32 | +13 | 69 | 0.75 | 0.49 | 0.28 | +11 | -9 | +4.2 |
| Per-coin MA trend (20/50/100/200 ensemble) [walk-forward] | +48 | +233 | -41 | +34 | +15 | -41 | +8 | 60 | 0.59 | 0.50 | 0.36 | +12 | -16 | +3.8 |
| Donchian ensemble, vol-targeted | +27 | +23 | -6 | +9 | +10 | -3 | +2 | 15 | 1.08 | 0.09 | 1.72 | +18 | -5 | +3.9 |
| XS nearness to 52-week high | +317 | +346 | -65 | +134 | +84 | -40 | +30 | 85 | 1.01 | 1.00 | 0.20 | +18 | -8 | +7.4 |
| XS nearness to 52-week high [walk-forward] | +280 | +334 | -70 | +134 | +84 | -40 | +30 | 88 | 0.96 | 1.00 | 0.18 | +15 | -7 | +6.5 |
| BTC-dominance rotation (30d) | +161 | +281 | -66 | +82 | +59 | -13 | -8 | 81 | 0.86 | 1.00 | 0.20 | +14 | -1 | +0.1 |
| BTC-dominance rotation (30d) [walk-forward] | +159 | +133 | -66 | +82 | +80 | -25 | -8 | 86 | 0.74 | 1.00 | 0.20 | +12 | -3 | +0.1 |
| BTC Monday effect | +44 | -27 | -25 | -18 | +22 | -24 | +7 | 64 | -0.16 | 0.14 | 0.30 | -1 | -7 | +2.3 |
| BTC turn of month | -7 | +47 | -12 | -5 | -30 | +10 | -10 | 51 | -0.01 | 0.13 | 0.42 | +0 | +4 | -4.1 |

Beat System 11 at equal risk (2020-25 avg > +35%): Dual momentum BTC/ETH (12m)
Beat System 11 in 2025 at equal risk (> +8%): none
Beat System 11 in 2026 YTD at equal risk (> +1.5%): EW basket of members, EW basket when BTC > MA100, BTC MA-ratio rules (5-100d ensemble) [walk-forward], XS high idiosyncratic vol (30d), XS high idiosyncratic vol (30d) [walk-forward], XS illiquidity (Amihud 30d), Per-coin MA trend (20/50/100/200 ensemble), Per-coin MA trend (20/50/100/200 ensemble) [walk-forward], Donchian ensemble, vol-targeted, XS nearness to 52-week high, XS nearness to 52-week high [walk-forward], BTC Monday effect
All three: none

## Sources and rules

| strategy | source | rule | published claim |
|---|---|---|---|
| BTC buy & hold | benchmark | 100% BTC | - |
| EW basket of members | benchmark (LTW CMKT analogue, equal weight) | 1/N of every member, held continuously | - |
| EW basket when BTC > MA100 | benchmark (System 11 gate) | EW basket while BTC close > 100-day MA, else cash | - |
| XS momentum (top third, 3-week) | Liu, Tsyvinski & Wu (2022) J. Finance 'Common risk factors in cryptocurrency' | weekly: long the top third of members by past 3-week return, equal weight | CMOM 3-week long-short ~3%/week, t>3 (2014-2018) |
| XS size (small third, turnover proxy) | Liu, Tsyvinski & Wu (2022) J. Finance | weekly: long the smallest third of members (size proxied by mean daily USD volume, no market cap on disk) | CSIZE small-minus-big ~3%/week (2014-2018) |
| BTC TS momentum (1-week) | Liu & Tsyvinski (2021) RFS 'Risks and returns of cryptocurrency' | weekly: hold BTC next week if its past-week return > 0, else cash | past 1-week return predicts 1-8 weeks ahead; long-cash Sharpe above buy & hold |
| BTC MA-ratio rules (5-100d ensemble) | Detzel, Liu, Strauss, Zhou & Zhu (2021) Financial Management | daily: BTC exposure = share of n in {5,10,20,50,100} with close > MA(n), rest in cash | OOS R2 > 0 and Sharpe ~2x buy & hold (2011-2018) |
| XS short-term reversal (1-day) | Zaremba, Bilgin, Long, Mercik & Szczygielski (2021) IRFA 'Up or down?' | daily: long the bottom third of members by yesterday's return | daily reversal premium, strongest in small illiquid coins |
| XS low volatility (30d) | Burggraf & Rudolf (2021) J. Asset Mgmt 'Cryptocurrencies and the low volatility anomaly' | weekly: long the lowest-volatility third of members (30-day daily std) | low-vol portfolios beat high-vol on a risk-adjusted basis |
| XS high idiosyncratic vol (30d) | Zhang & Li (2020) RIBAF 'Is idiosyncratic volatility priced in crypto?' | weekly: long the top third of members by 30-day residual vol vs the EW market | positive IVOL-return relation, significant |
| XS illiquidity (Amihud 30d) | Zhang & Li (2021) FRL / Wei (2018) Econ. Letters - illiquidity premium | weekly: long the most illiquid third of members (mean |r|/USD volume, 30 days) | illiquid coins earn higher next-week returns |
| Dual momentum BTC/ETH (12m) | Antonacci (2014) 'Dual Momentum Investing', applied to BTC/ETH | monthly: hold the better of BTC/ETH by 12-month return if it is > 0, else cash | equity/bond evidence; crypto use is practitioner |
| Vol-scaled TSMOM (12m, 40% vol) | Moskowitz, Ooi & Pedersen (2012) JFE | monthly: per member coin, long if 12-month return > 0, sized 40%/ex-ante vol (cap 1), 1/N each | TSMOM Sharpe > 1 across 58 futures (1985-2009) |
| Vol-scaled TSMOM (1/3/12m blend) | Hurst, Ooi & Pedersen (2017) 'A century of evidence on trend-following' | monthly: per coin signal = mean sign of 1/3/12-month returns (long part only), sized 40%/vol, 1/N each | positive in every decade since 1880; crypto use is practitioner |
| Per-coin MA trend (20/50/100/200 ensemble) | Hudson & Urquhart (2021) Ann. Oper. Res.; Corbet et al. (2019) FRL | daily: each member coin gets 1/N x share of n in {20,50,100,200} with close > MA(n) | MA rules show significant predictability and beat buy & hold in crypto |
| Donchian ensemble, vol-targeted | Zarattini, Pagani & Barbon (2025) SFI 25-80 'Catching crypto trends' | daily: per coin, mean over 9 lookbacks (5..360d) of breakout state with midpoint trailing stop, sized 25%/vol90 (cap 1 spot), 1/N | top-20 rotating portfolio: net Sharpe > 1.5, alpha 10.8%/yr vs BTC |
| XS nearness to 52-week high | Jia, Simkins, Yan, Zhang & Zhao (2025) SSRN 5386180 (George & Hwang 2004 in crypto) | weekly: long the third of members closest to their 365-day high | significant positive Nearness52 premium in the cross-section |
| BTC-dominance rotation (30d) | practitioner ('altseason' index, blockchaincenter.net) | weekly: hold the EW alt basket if its 30-day return beats BTC's, else hold BTC | no peer-reviewed evidence |
| BTC Monday effect | Caporale & Plastun (2019) FRL 'The day of the week effect in the cryptocurrency market' | hold BTC only during Mondays (UTC), cash otherwise | abnormally high BTC returns on Mondays (2013-2017) |
| BTC turn of month | Kaiser (2019) FRL 'Seasonality in cryptocurrencies' (equity ToM rule) | hold BTC from the last day of a month through day 3 of the next, cash otherwise | mixed: most crypto seasonalities do not survive |

## Caveats

- The universe is small (6 members in 2020, 13-14 later at cap 14): cross-sectional terciles are 2-5 coins, so factor results are noisy and differ in kind from the papers' 500-2000-coin samples.
- No market caps on disk: size is proxied by mean daily USD volume (overlaps with illiquidity).
- The papers' samples mostly end before 2020; our 2020-2026 test is genuinely out of their sample.
- Equal-risk rescaling multiplies daily returns (costs included) and assumes leverage is available when k > 1.
- 2026 is to date; one partial year is not evidence either way.
## Verdict (2026-10-21, written by hand after the run)

- Nothing beats System 11 on all three counts (equal-risk 2020-25 average, 2025, 2026). No classic matches its 2020-25 Sharpe of 1.40; the best are Donchian (1.16), dual momentum (1.18 published, 0.90 walk-forward) and low-vol walk-forward (1.20).
- Only dual momentum BTC/ETH at the published 12-month lookback edges System 11 at equal risk (+38 vs +35), and almost all of that is 2021. Picking the lookback walk-forward drops it to +18, so the edge is the parameter, not the rule.
- Donchian ensemble (Zarattini et al.): best risk shape (DD 15%, 10% average exposure), but at equal risk it averages +20 and is negative in 2025. It is a candidate overlay or diversifier, not a replacement.
- Cross-sectional factors (momentum, size, illiquidity, IVOL, 52-week high) do no better than the EW basket in a 6-14 coin universe. 1-day reversal is wiped out by costs (it turns the book over daily). Calendar effects are noise.
- The plain "basket when BTC > MA100" gate is the strongest classic (+34 equal-risk, +26% in 2026 at cap 14). That is System 11's own gate, so the gate itself, not the MLP ranking, carries much of the edge.
