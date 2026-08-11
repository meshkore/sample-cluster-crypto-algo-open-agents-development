---
id: global-market-trend
title: "The global market trend: what the market is, and when it turns"
status: active
priority: critical
oneliner: "Detect the major trend from the whole market rather than six survivors, and find whether its segments turn in a queue."
modules: [quantlab, design, tests]
target: "continuous"
created: 2026-08-11
updated: 2026-08-11
owner: unassigned
related: [liquid-ml-research]
---

## Why this exists

Every strategy in this laboratory is routed by one label: what major trend is
the market in? The operator's argument is that this trend is a property of the
**whole market** — a bull run ends at peak total capitalisation and a bear ends
at the trough — and that the detector was answering it from six surviving
assets.

Two measurements taken on 2026-08-11 say the concern was justified, and that
the second half of the intuition is not yet supported.

### The market was too small, and breadth is the reason

`orchestrator-manager/scripts/market_shootout.py` (H-L086M) built four
candidate markets over 385 assets and 3,059 bars and scored each against the
**same** broad benchmark, so no variant could win by being easy to predict:

| market | BEAR | SIDEWAYS | BULL | ordered | BEAR in 2024-26 |
|---|---|---|---|---|---|
| basket-6-equal (incumbent) | −2.15% | −4.16% | +3.70% | no | 34.0% |
| **universe-equal (adopted)** | **−2.43%** | **+1.01%** | **+4.01%** | **YES** | **57.1%** |
| universe-sqrt | −2.38% | −0.45% | +4.57% | YES | 57.0% |
| universe-turnover | −1.34% | −5.33% | +5.60% | no | 48.1% |

The six-name basket is **not correctly ordered against the market it claims to
describe**: its SIDEWAYS bucket falls harder than its BEAR bucket. The whole
listed universe is ordered, and it nearly doubles the bear branch's training
signal in the fold that falls.

The sharper reason is breadth. On six names breadth can only report 0, 1/6,
2/6 … against thresholds at 0.35 and 0.50 — so the difference between a bull
market and a bear one was **one asset changing its mind**.

One honest disagreement is preserved rather than resolved: turnover weighting
was the only variant right in **all four folds** (−1.20%, −2.35%, −0.78%,
−4.46% BEAR-minus-BULL) while failing the pooled ordering. Both are searchable
dimensions so the full objective, not this scorecard, settles it.

### Capitalisation is not computable here, and that is a data gap

True market capitalisation is price × circulating supply. **This laboratory
holds no supply data at all** — the archive is Binance OHLCV. Every index above
is a proxy, and turnover weighting is the closest one available. Acquiring
supply is #QUANT21, not a footnote.

A second limitation of the same kind: the composite chains weighted mean
returns, so it moves only when prices move. A real capitalisation index is a
**sum** and moves when a coin is issued. That difference is why nothing here is
called a capitalisation index.

### The lead-lag hypothesis is not supported at daily resolution

`orchestrator-manager/scripts/cohort_lag.py` assigned every asset to a cohort
from listing date and turnover alone — no external taxonomy exists in this
archive — and cross-correlated each cohort against the whole market at every
lag from −90 to +90 days.

**The correlation peaks at lag 0 for every single cohort.** No cohort leads or
follows the market in daily returns.

What the same measurement *did* find is structure of a different shape:

| cohort | assets | peak | now below peak | corr to market |
|---|---|---|---|---|
| BTC | 1 | 2025-08-14 | 24% | 0.779 |
| majors (top-decile turnover, pre-2021) | 12 | 2021-11-23 | 57% | 0.940 |
| established alts (pre-2021) | 91 | 2018-02-04 | 98% | 0.953 |
| retail-era alts (2021-22) | 86 | 2021-04-17 | 98% | 0.694 |
| recent listings (2023+) | 195 | 2024-04-04 | 94% | 0.457 |

Two things worth more than the refuted lag:

- **The cohorts peaked in different cycles and never came back.** BTC made a
  new high in 2025; the established alts topped in **February 2018** and sit 98%
  below it. "The market" is not one series with one cycle — it is a small set of
  survivors and a very long tail that has been in a bear market for seven years.
- **Recent listings correlate only 0.457 with the market.** They are the least
  explained cohort by a distance, which is where an independent signal would be
  if one exists.

## Task plan

- #QUANT20 **done** — the market is the whole listed universe; weighting is searchable.
- #QUANT21 pending — acquire circulating supply so capitalisation is computable at all.
- #QUANT22 pending — find the turn, not the co-movement: the lag test was on returns.
- #QUANT23 pending — cohorts from behaviour rather than from listing date.
- #QUANT24 pending — a cohort-aware detector, if and only if #QUANT22 finds a lead.
- #QUANT25 pending — stablecoin flows and dominance as a regime input.
- #QUANT26 pending — show the market composite in the monitor, beside the equity.

## What this initiative may not do

Historical optimisation ends 2025-12-31. Every measurement here was taken on
the fittable era; 2026 is never an input. Any cohort or index defined by
looking at 2026 is fitted to the answer and is worthless.
