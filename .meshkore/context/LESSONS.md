# What this laboratory has already learned

*Generated from every system's `docs/context.json` by
`python -m quantlab_catalog.lessons`. Do not edit by hand — edit the system's own
record and regenerate, or the two will disagree and this is the one people read.*

**Read this before opening a new system.** Almost every rule below was bought with a
measurement that cost real time, and several were bought with a sealed year — a
resource that does not regenerate. Re-deriving them is the most expensive way to spend
a week that this laboratory offers.

**33 rules from 7 systems.**

## The oracle-taught net
`system06` · champion · [its full record](../../trading-system/quantlab_system06/docs/SUMMARY.md)

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
`system07` · workshop · [its full record](../../trading-system/quantlab_system07/docs/SUMMARY.md)

1. Two books beat one when their losses land in different regimes - the capitulation book earns inside the drawdowns that hurt the trend book, which is why the combine lifts the worst year rather than the median.
2. Dose curves in this laboratory overshoot at 1.0. Measure the response, take the half-dose, and do not assume more of a good lever is better.
3. A caveat recorded at the time of the measurement is worth more than one reconstructed later - the year-start cash overdraw was known on the day and is still the first thing to fix.

## The intraday system (5m)
`system-intraday` · frozen · [its full record](../../trading-system/quantlab_intraday/docs/SUMMARY.md)

1. This market has no bell. Any rule that closes, resets or aggregates on a session boundary is importing an assumption from equities.
2. A sealed window can only measure a rule that actually trades in it - check the trade count before reading the return.
3. The incumbent bar for this laboratory is +5.05% sealed 2026 (24 trades, 7.88% drawdown). Every later generation is measured against that number.

## The original rule grammar
`system-trading` · frozen · [its full record](../../trading-system/quantlab_trading/docs/SUMMARY.md)

1. The universe is every asset LISTED AT THE TIME, never the ones that survived to today. Survivorship is the easiest large error to make here and the hardest to see afterwards.
2. Size by volatility, not by name. Equal notional across unequal assets is a risk decision disguised as a neutral one.
3. A label is a measurement. Check what the bear label SELECTED before trusting anything conditioned on it.

## Generation four - the machine-written workshop
`system04` · frozen · [its full record](../../trading-system/quantlab_system04/docs/SUMMARY.md)

1. Making a configuration trade MORE often pays the toll more often; it does not manufacture an edge. Anyone proposing to rescue a configuration by raising its frequency owes an answer to generation four.
2. +495% training producing a forward loss is the strongest anti-prediction datum on record here: training return does not rank forward return.
3. A gate that refuses CORRECT code fails silently and is as bad as one that permits bad code - the author is told a rule it is breaking, the rule does not exist, and it cannot comply.
4. A watchdog that reports 'ok' while nothing is achieved is not a watchdog. Liveness is not progress, and only progress is worth alerting on.

## Generation five - meta-labelled ITSM
`system05` · frozen · [its full record](../../trading-system/quantlab_system05/docs/SUMMARY.md)

1. Both halves of a publish must carry identical --set flags. `trade_from` is the only thing training and forward may differ on.
2. A filter is the only change that can improve the return AND the bill at the same time - at 30 bps round trip an extra trade is a certain cost against an uncertain gain.
3. Score a model only on rows a fold model never saw; research verdicts come from the purged walk-forward, sealed rows from the model fitted before the lock.

## Open — no hypothesis yet
`system08` · blank · [its full record](../../trading-system/quantlab_system08/docs/SUMMARY.md)

1. RECURSIVE SELF IMPROVEMENT: when the loop loses, ask which GATE was missing, not which lever was wrong. A run that only produces a better strategy has not improved the loop.
2. 2-of-2 walk-forward exams before a sealed reading
3. price the edge: a spread straddling 1.0 cannot be settled by one year
4. a stage is cleared once; re-running an exam until it passes is selection
5. Absorption (H1-R) is DEAD at 15m and was killed cheaply: on 74,181 clustered events over 2,985 days and 9 years, the impact residual adds +0.08 bps at 60m to what signed flow alone already gives (t=0.09). Do not re-open it without a 5m test that first answers why R02 saw nothing. See research/system08/rnd/r02_h1r_screen_2026-09-09.json.
6. Signed order flow at 15m is not tradeable on our universe: the TOP flow decile earns -0.01 bps at 60m before costs, against a 30 bps round trip. The permanent same-direction effect the literature reports (Anastasopoulos et al., JFM 2026) does not survive our resolution and our cost model.
7. Over-extension is the one structure the flow screen surfaced, and it FAILED its own registered test: flow that moves price more than expected gives it back, monotonically in the residual and with the same sign in 8 of 9 years - but only -3.13 bps at the registered 60m horizon, under the 5 bp line. It reaches -8.53 bps (t=-4.35) at 4 hours. Reading THAT as a pass would be moving the goalposts after seeing the data, which is how the deep-field net, the 5-seed ensemble and recency weighting all reached a sealed reading and lost it. If the 4h horizon is worth testing it needs its own pre-registration, not a rescued one.
8. Screen at the resolution you already own before buying a finer one. taker_buy_volume has been in our 15m candles since 2017; the absorption question was answerable in an afternoon with 2.96M bars and no download, against the week and 30 GB of aggTrades the pre-registered version needs. Build the cheap test so that it can only give bad news, then let bad news be free.

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
