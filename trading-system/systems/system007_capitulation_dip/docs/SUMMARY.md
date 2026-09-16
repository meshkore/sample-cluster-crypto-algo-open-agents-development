# CapitulationDip - the drop-regime book

*Status: **workshop** · opened 2026-08-28, still open.*

> Written from this system's own measured record — its README tables, the task
> records under `.meshkore/modules/`, and its commit bodies. Every figure below
> carries the source that holds it, so a reader who distrusts a number can check
> the same place I did.

## 1. Hypothesis

System 06 loses in drop regimes. A long-only capitulation dip-buyer earns in exactly those regimes, so a 06+07 combine raises the rolling one-year win rate without the median cost a breadth-gated single system pays.

## 2. What it is

Per symbol: open long when the causal capitulation score exceeds `enter`; close on a bounce target, a stop, or a maximum horizon. Equal-fraction sizing, capped concurrent names, shared cash, 0.003 round trip.

**Data consumed:**

- 15m candles, the system 06 universe, via the shared catalogue
- system 06's causal capitulation score as the entry feature

## 3. What helped

- **A 30% cash sleeve of the capitulation book over the balanced trend book** — every thin research year lifts (worst year 5.1% -> 7.6%) and combined drawdown falls in 6 of 8 years (2021 17.4% -> 10.8%) - the bounce-buyer earns inside the crashes that draw the trend book down *(A64 stage 3, e9c57a9)*
- **drop_sizing at dose 0.5** — expectancy concentrates in deep flushes - the top drop quartile pays +3.89% per trade at 72% win *(5c00600)*
- **Measuring the package through system007_capitulation_dip.combine rather than by hand** — package v2: worst year +8.3%, 2022 +17.7% at 3.5% drawdown, 2018 +41.3% at lower drawdown than the trend book alone, 2021 +1196.7% at 12.0% *(5c00600)*

## 4. What hurt

*This section matters more than the one above: it is the part that cannot be
reconstructed from the code.*

- **Sizing the sleeve once at the start of the year** — overdraws cash in growth years; a monthly rebalance is the recorded fix and has not been done *(e9c57a9, caveat recorded at the time)*
- **drop_sizing at dose 1.0** — overshoots - the same shape as every dose curve measured that week, which is why 0.5 was taken *(5c00600)*

## 5. What is still open

- **Monthly rebalance of the cash sleeve** — the year-start sizing is known to overdraw in growth years and the fix was deferred, not tested
- **A sealed reading of the combine** — every number above is a research-era number; the package has never been read on a sealed year

## 6. Rules learned

1. Two books beat one when their losses land in different regimes - the capitulation book earns inside the drawdowns that hurt the trend book, which is why the combine lifts the worst year rather than the median.
2. Dose curves in this laboratory overshoot at 1.0. Measure the response, take the half-dose, and do not assume more of a good lever is better.
3. A caveat recorded at the time of the measurement is worth more than one reconstructed later - the year-start cash overdraw was known on the day and is still the first thing to fix.
