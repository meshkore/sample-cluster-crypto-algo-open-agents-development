---
id: TRADE2
title: "H-INTRA-002: buy the morning move, hold days, and let the winner run"
status: in_progress
priority: high
owner: unassigned
category: trading-system
initiative: intraday-second-system
created: 2026-08-12
updated: 2026-08-12
tags: [intraday, 5m, momentum, time-series-momentum, costs, hypothesis]
depends_on: [TRADE1]
blocks: []
---

## Where this came from

TRADE1 refuted reversion and left a design rule: reversion's target IS the
anchor, so its mean payoff is bounded near the toll however high the win rate.
What can clear a fixed 0.30% round trip is a rule whose right tail is open.

`survey.py` then measured fourteen candidate mechanisms in one pass -- each with
published evidence or a structural reason for an uncapped payoff -- across five
majors and 4.3M 5-minute bars. **At 1h to 24h horizons not one of them beats
drift after costs in either era**, the published intraday-momentum rule
included. That is not a contradiction of the papers: they report breakeven
costs of 3-10 bps and this laboratory models 30. `survey.py` now prints a
`be bps` column so the comparison is explicit.

At 72h the table changes.

## The signal

**At 06:00 UTC, when the day is already up 1.5%, buy and hold three days.**

Five symbols, non-overlapping windows only, net of the 0.30% round trip and
measured as excess over the same-horizon drift:

| entry threshold | excess 2017-2022 | excess 2023-2025 |
|---|---|---|
| 0.0% | −0.404% | −0.399% |
| 0.5% | −0.304% | −0.101% |
| 1.0% | −0.104% | −0.014% |
| **1.5%** | **+0.126%** | **+0.543%** |
| 2.0% | +0.033% | +0.919% |
| 3.0% | +0.490% | +2.489% |

Monotone in both eras, positive on all five symbols in both eras, breakeven
72.7 bps. The **dose-response** is what makes it a mechanism rather than a
lucky cell: a bigger morning move buys a bigger reward.

## What keeps it honest

- t on the excess is **0.4 in discovery, 1.6 in validation**. Weak. Only the
  2.0-3.0% thresholds reach 2-3, and those fire ~100 times in three years.
- The **median trade is negative** (−0.275% discovery, 48% of trades positive).
  Tail-driven by construction, which is what H-INTRA-002 set out to find and
  also what produces long losing streaks.
- Not cycle-agnostic: 2018 −0.44%, 2022 −1.43%, 2025 −0.06% against 2021 +1.86%
  and 2023 +2.32%. Long-only momentum in a falling market is a losing trade.

## Portfolio results — six variants over eight 90-day blocks, 2017-2025

Same entries throughout (`itsm`, 06:00 UTC, 1.5%, three-day hold, five majors).
Only the exit and the filter change. `w/o best` is the mean with the single
best block removed — the cheapest test of whether a mean is a mechanism or one
lucky window.

| | stop | trend filter | risk | mean | median | +blocks | worst block | maxDD | trades | w/o best |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 7% | — | 1.75% | +0.55% | −0.07% | 4/8 | −21.90% | 22.17% | 264 | −2.37% |
| B | none | — | 5% | +4.24% | +2.03% | 4/8 | −20.10% | 21.66% | 238 | −1.79% |
| C | 7% + 12% trail | — | 1.75% | −0.89% | −1.54% | 4/8 | −21.90% | 22.17% | 266 | −3.31% |
| D | 7% | 30-day | 1.75% | +2.16% | +5.23% | 5/8 | −11.16% | 18.01% | 147 | −0.04% |
| E | 7% | 14-day | 1.75% | +0.59% | +3.41% | 5/8 | −17.11% | 17.71% | 163 | −1.22% |
| **F** | **none** | **30-day** | **5%** | **+2.69%** | **+2.41%** | 4/8 | **−10.04%** | **17.31%** | 133 | **+0.25%** |

Two findings, each measured independently before they were combined:

- **Truncating the winner costs money.** C < A < B, monotone, on identical
  entries: a trailing stop is worse than a stop, and a stop is worse than none.
  This is the central claim of H-INTRA-002 — a mechanism that pays through its
  right tail cannot afford to have that tail clipped — and it is now measured
  three ways rather than argued.
- **The trend filter buys drawdown, not return.** A → D cuts the worst block
  from −21.9% to −11.2% and maxDD from 22.2% to 18.0%, at the cost of 117 of
  264 trades. Justified by prior (Moskowitz/Ooi/Pedersen on the regime
  dependence of time-series momentum), not by the block that lost money.

## The configuration, fixed on training evidence — variant F

    entry_rule=itsm  itsm_hour=6  itsm_threshold=0.015
    maximum_holding_bars=864  exit_end_of_day=false  maximum_positions=3
    stop_atr=60  trail_atr=0  risk_per_trade=0.05  trend_ma_days=30

Chosen because it keeps both findings, has the lowest worst block and the
lowest maximum drawdown of the six — the 25% abort is the constraint that
actually binds here — and is **the only variant whose mean survives deleting
its best block**. B's entire mean is one window: 2021 paid +46.45% and without
it B averages −1.79%.

What this is not: a statistically separated winner. Eight blocks cannot
distinguish D, E and F, and the honest reading is that the mechanism's evidence
is the signal study — dose-response, five symbols, two eras — while the block
table only shows that a portfolio built on it survives different tape.

## The training half, continuous — and the abort the blocks hid

    intraday-itsm-30d-training   +168.19%   maxDD 25.04%   388 trades   STOPPED
    drawdown mandate breached: equity 268,193 is 25.04% below the peak 357,794
    last active 2022-04-08

One continuous run from 2018-01-01. It turned 100,000 into 357,794 by May 2021,
gave back a quarter of that peak, and **the 25% mandate ended the evaluation on
2022-04-08** — so it never traded 2022-2025 at all. Pre-cost +210.59%; the toll
took 42.4% of capital across 388 trades.

**The eight blocks could not have shown this and it is worth saying why.** Every
block starts again at 100,000, so no block can express a drawdown that builds
across years: F's worst block was −10.04% and its worst block drawdown 17.31%,
all comfortably inside the budget. Compounded continuously the same rule reaches
25% peak-to-trough and is stopped. Block statistics measure whether a mechanism
survives different tape; they say nothing about the path a real account takes
through all of it, and this pair is the demonstration.

Two things this is not. It is not a loss — drawdown **from initial capital**
peaked at 13.97%, and the run was up 168% when it was stopped. And it is not the
mandate misfiring: giving back a quarter of the peak is exactly what the rule
exists to stop, and the rule is not negotiable.

What it changes: the next hypothesis on this mechanism has to carry a
portfolio-level de-risk, not only per-trade sizing. That is a new configuration
and it gets its own forward run — this one is spent.

## The sealed window, opened once

    intraday-itsm-30d-2026   +5.05% net   maxDD 7.88%   24 trades   complete

Pre-cost +7.26%; the toll took 2.2% of capital. One run, the parameters above
unchanged, `trade_from` the only difference from the training half — and it was
run after the configuration was written down, not before.

Read against the market rather than against zero: **2026 fell 22.6%**, and this
is +5.05% long-only with 7.88% peak drawdown, well inside the 25% abort. It is
the best 2026 result on the monitor, ahead of the previous champion
(`loop-101-detector-2026`, +1.89%).

What it does not prove. **24 trades** is a small sample, and this mechanism is
tail-driven by construction: the median trade is negative and 48% of trades are
positive, so a handful of the 24 carry the number. A 30-day trend filter in a
falling year mostly stands aside, which is why drawdown is low and why the
result depends on the few windows it did trade. The honest claim is that the
mechanism behaved in the sealed window the way training said it would, not that
+5.05% is its expected return.

## Not yet done

- A walk-forward over more than eight blocks.
- More symbols. Five majors is what the signal study covered; the capacity
  floor would allow far more, and 24 trades a year is the argument for it.
