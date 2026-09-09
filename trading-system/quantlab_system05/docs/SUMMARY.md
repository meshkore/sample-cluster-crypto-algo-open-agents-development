# Generation five - meta-labelled ITSM

*Status: **frozen** · opened 2026-08-13, closed 2026-08-13.*

> Written from this system's own measured record — its README tables, the task
> records under `.meshkore/modules/`, and its commit bodies. Every figure below
> carries the source that holds it, so a reader who distrusts a number can check
> the same place I did.

## 1. Hypothesis

The incumbent has edge and no discretion. Add a secondary model that declines the entries that resolve downward, and change nothing else - a filter is the only move that can improve the return and the toll at the same time.

## 2. What it is

Meta-labelling (Lopez de Prado ch.3) over the 06:00 UTC 1.5% morning-move entry. Primary picks the side, secondary picks the size, and the sizes are one and zero.

**Data consumed:**

- 5m candles, five USDT majors, via the shared catalogue
- 46 features from quantlab_ml.dataset.build, precomputed into a verdict table

## 3. What helped

- **The meta-labelling filter (a secondary model declines entries the primary would take)** — halves the trade count in the overlapping years - 161 against 318 across 2019-2021 - holds drawdown under the mandate, and so the run lives through the whole research era instead of dying on 2022-04-08. The first rule in this laboratory to finish the training era inside the 25% mandate *(README.md, run pair eff92b31de88cadb)*
- **Precomputing verdicts with the SAME dataset.build call used to train** — a brain recomputing 46 features live would be a second implementation of that arithmetic, and drift would feed the model garbage while every metric on the page read normally *(README.md)*
- **Treating a missing verdict as a refusal** — bars before the first walk-forward test block have no honest verdict; letting them trade unfiltered would produce a card describing no strategy at all *(README.md)*
- **Composing the primary from the champion instead of copying it** — 'generation 5 minus the filter' IS the incumbent, so the run measures exactly one variable *(README.md)*

## 4. What hurt

*This section matters more than the one above: it is the part that cannot be
reconstructed from the code.*

- **The filter's discrimination on the sealed year** — it inverts. Of the incumbent's setups it approved 7, and among them kept the single worst trade of the year (SOL -10.74%) while declining the July SOL entry that was the incumbent's best (+10.83%) *(README.md, sealed 2026)*
- **A POLICY key falling back to its default** — generation 5 took no trades at all, and the run looked like a strategy with no signal rather than a configuration bug *(4d5492d)*

## 5. What is still open

- **Whether the filter's inversion on 2026 is real or small-sample** — it is a 7-trade sealed window; the same filter halved trades and held the mandate across seven research years

## 6. Rules learned

1. Both halves of a publish must carry identical --set flags. `trade_from` is the only thing training and forward may differ on.
2. A filter is the only change that can improve the return AND the bill at the same time - at 30 bps round trip an extra trade is a certain cost against an uncertain gain.
3. Score a model only on rows a fold model never saw; research verdicts come from the purged walk-forward, sealed rows from the model fitted before the lock.
