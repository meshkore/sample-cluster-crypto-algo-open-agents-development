# What this laboratory has already learned

*Generated from every system's `docs/context.json` by
`python -m quantlab_catalog.lessons`. Do not edit by hand — edit the system's own
record and regenerate, or the two will disagree and this is the one people read.*

**Read this before opening a new system.** Almost every rule below was bought with a
measurement that cost real time, and several were bought with a sealed year — a
resource that does not regenerate. Re-deriving them is the most expensive way to spend
a week that this laboratory offers.

**40 rules from 8 systems.**

## The oracle-taught net
`system06` · champion · [its full record](../../trading-system/systems/system006_oracle_net_15m/docs/SUMMARY.md)

1. A candidate needs 2-of-2 walk-forward exams before a sealed reading. One exam year is a coin flip.
2. Price the odds first: if the candidate's per-year ratio spread against the incumbent straddles 1.0, one sealed year cannot settle it - do not spend the reading.
3. 'Held out' in a threshold study means held out from the THRESHOLDS, not the NET. Score net-sensitive levers on a walk-forward net.
4. A joint Bayesian search never measures one-lever neighbours of its own anchor - ablate separately.
5. Check an 'off' value against the code. max_drawdown=0.0 is the TIGHTEST brake, not the absent one.
6. Turnover levers fitted on the full record describe a dead market: fast rotation paid 2.97x in 2018 and 0.82x in 2024.
7. Run every tool from the repo root with PYTHONPATH=trading-system or the universe silently degenerates.
8. Compare growth multiples - ratios of (1+r) - never differences of percentages.
9. Trend-following gives up bull upside to avoid bear catastrophes; the +30%-every-year mandate is not reachable by this book alone.

## CapitulationDip - the drop-regime book
`system07` · workshop · [its full record](../../trading-system/systems/system007_capitulation_dip/docs/SUMMARY.md)

1. Two books beat one when their losses land in different regimes - the capitulation book earns inside the drawdowns that hurt the trend book, which is why the combine lifts the worst year rather than the median.
2. Dose curves in this laboratory overshoot at 1.0. Measure the response, take the half-dose, and do not assume more of a good lever is better.
3. A caveat recorded at the time of the measurement is worth more than one reconstructed later - the year-start cash overdraw was known on the day and is still the first thing to fix.

## The Ledger - reconstructed-participant market simulation
`system09` · workshop · [its full record](../../trading-system/systems/system009_participant_ledger/docs/SUMMARY.md)

1. A trade redistributes cash inside the ecosystem; it does not add any. Only the boundary - issuance, listings, stablecoin mint and burn, ETF creation, fiat - changes the totals.
2. Exchange tape is anonymous: participants are latent cohorts pinned by accounting identities and external anchors, never reconstructed wallets.
3. One wallet, many assets: giving each market its own pile of cash invents liquidity, and competition for one pool is most of what modelling an ecosystem means.
4. What cannot be observed should be inferred and REPORTED, never assumed. A residual that must fade over time is a falsifiable prediction; an assumption is not.
5. Check the base of any growth factor before using it as a driver: a series that starts near zero produces an infinite growth rate and saturates whatever it drives.
6. Wanting and being able to are both required: an allocator that uses capacity only as a cap, never as a weight, silently deletes its own size distribution.
7. A cohort is defined by its turnover, not only by its opinion.
8. Forced flow must be allocated before discretionary flow, or a structural seller stops being structural and changes sign.
9. A held-out anchor is evidence only when scored against the signal that drove the prediction.
10. Declare a verdict on a vote over every statistic computed, never on the best one.

## The original rule grammar
`system01` · frozen · [its full record](../../trading-system/systems/system001_rule_grammar_daily/docs/SUMMARY.md)

1. The universe is every asset LISTED AT THE TIME, never the ones that survived to today. Survivorship is the easiest large error to make here and the hardest to see afterwards.
2. Size by volatility, not by name. Equal notional across unequal assets is a risk decision disguised as a neutral one.
3. A label is a measurement. Check what the bear label SELECTED before trusting anything conditioned on it.

## The intraday system (5m)
`system02` · frozen · [its full record](../../trading-system/systems/system002_intraday_momentum_5m/docs/SUMMARY.md)

1. This market has no bell. Any rule that closes, resets or aggregates on a session boundary is importing an assumption from equities.
2. A sealed window can only measure a rule that actually trades in it - check the trade count before reading the return.
3. The incumbent bar for this laboratory is +5.05% sealed 2026 (24 trades, 7.88% drawdown). Every later generation is measured against that number.

## Generation four - the machine-written workshop
`system04` · frozen · [its full record](../../trading-system/systems/system004_llm_written_rules/docs/SUMMARY.md)

1. Making a configuration trade MORE often pays the toll more often; it does not manufacture an edge. Anyone proposing to rescue a configuration by raising its frequency owes an answer to generation four.
2. +495% training producing a forward loss is the strongest anti-prediction datum on record here: training return does not rank forward return.
3. A gate that refuses CORRECT code fails silently and is as bad as one that permits bad code - the author is told a rule it is breaking, the rule does not exist, and it cannot comply.
4. A watchdog that reports 'ok' while nothing is achieved is not a watchdog. Liveness is not progress, and only progress is worth alerting on.

## Generation five - meta-labelled ITSM
`system05` · frozen · [its full record](../../trading-system/systems/system005_meta_label_filter/docs/SUMMARY.md)

1. Both halves of a publish must carry identical --set flags. `trade_from` is the only thing training and forward may differ on.
2. A filter is the only change that can improve the return AND the bill at the same time - at 30 bps round trip an extra trade is a certain cost against an uncertain gain.
3. Score a model only on rows a fold model never saw; research verdicts come from the purged walk-forward, sealed rows from the model fitted before the lock.

## The Residual Book - cross-sectional residual momentum, long and short
`system08` · closed · [its full record](../../trading-system/systems/system008_residual_momentum_ls/docs/SUMMARY.md)

1. A constraint stated in a formula must be enforced on every bar, not at every decision. 'Subject to sum|w| <= L' applied only at rebalances let the book lever itself to 2.67x by holding winners.
2. Inverse-volatility sizing needs a floor on the denominator: a name with no residual to own attracts the largest position in the book.
3. Declare the number of trials before reporting a Sharpe. Understating it is the specific lie the six dead systems were built on.
4. A first run that fails its registered bar is information, not a setback. Sweeping until it passes is exactly what the deflated Sharpe exists to punish.
5. 2026 was not read. The catalogue's lock is structural, not a convention.

---

## How to use this

A rule here is not advice, it is a **constraint that has already been tested**. If a new
hypothesis requires breaking one, that is allowed — but the break has to be argued
explicitly and measured, not walked past. The failure mode this document exists to
prevent is not disagreement; it is a system quietly re-running an experiment whose answer
is already written down.

The two rules that have cost the most, and that everything else tends to reduce to:

1. **Training return does not rank forward return.** System 04 measured +495.35% in
   training — the best figure ever produced here — and −5.81% on the sealed year.
2. **Price the odds before spending a sealed reading.** Three candidates were approved
   out of sample and lost the sealed year. The diagnosis was never "the edge is fake"; it
   was that a spread straddling 1.0 cannot be settled by a single year, and nobody
   computed the spread first.
