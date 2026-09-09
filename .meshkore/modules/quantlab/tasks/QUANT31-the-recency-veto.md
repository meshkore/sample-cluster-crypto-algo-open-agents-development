---
id: QUANT31
title: "Require the last two years to work, not the average of eight"
status: done
priority: critical
owner: master
category: quantlab
initiative: self-improving-arena
created: 2026-08-15
updated: 2026-09-09
tags: [objective, regime-decay, folds, 2026]
depends_on: [QUANT30]
blocks: []
---

# The recency veto

## Why — the measurement that produced it

Split every system the arena promoted at 2024-12-31, on the published training
curves:

| system | 2018–2024 | **2025 alone** | peaked | 2026 |
|---|---|---|---|---|
| r4 h14 0.750% 14d | +107.8% | **−13.5%** | 2025-10-07 | −4.19% |
| r6 h14 1.000% 10d | +85.6% | **−15.7%** | 2024-12-03 | −4.58% |
| r2 h15 2.500% 10d | +81.2% | **−7.6%** | 2024-11-24 | −3.14% |
| r3 h13 2.000% 7d | +71.1% | **−13.9%** | 2024-12-03 | −4.26% |
| r2 h14 2.000% 10d | +65.7% | **−3.0%** | 2025-10-07 | −2.91% |
| r5 h21 2.000% 7d | +56.7% | **−6.8%** | 2021-11-15 | −4.58% |

Six different trigger hours, thresholds from 0.75% to 2.5%. **All six positive
across 2018–2024, all six negative in 2025, all six negative in 2026.**

The sealed year was never a separate puzzle. It is year two of a decline that
begins inside the training data and is hidden because seven good years outweigh
one bad one in an eight-year sum. It is also why `unlucky` is the universal
killer on the engine's verdict: the peak sits in late 2024 or 2025, so the last
buyer is down 9–21%.

Optimising over 2018–2025 therefore selects for a regime that ended eighteen
months ago.

## What to do

`arena.measure` already walks four contiguous two-year folds and scores
`consistent` as the share that work. Make the FINAL fold a veto in its own right:
a genome that does not score in 2024–2025 is not a candidate, whatever its
average.

Shape it like `judgeable` — zero below a floor, one above it, a ramp between — so
the genetic search has a gradient to climb rather than a cliff to fall off. A
step function makes everything below the floor equally dead and no mutation is
ever rewarded for moving toward it.

## Why this is legal

2024–2025 is research era. The sealed window is not consulted, and this adds no
new channel from it. It is the same kind of statement as `consistent`: a claim
about WHEN the evidence is, not about what 2026 says.

## What it would have cost

Nothing but time saved. All six systems above would have been rejected at the
screen, before each spent about an hour of backtest and model fit.

## What to watch for

- Re-derive the incumbent floor after the change; `INCUMBENT_SIGNAL` will screen
  differently and the old floor is not comparable.
- Bump `SCREEN_VERSION` and say why. A row scored before and after this answers a
  different question.
- Clear `research/agent_runs/arena/archive.jsonl`. A surrogate fitted on both
  objectives learns the average of two different questions.
- Then restart the arena. It resumes from disk and re-derives the floor in
  seconds.

## The risk to state honestly

This is a recency bet, and it is one. If the 2025 decline is noise rather than
decay, the veto discards systems that would have recovered. The argument for it
is that six independent genomes agree, and that a system which lost money in the
most recent two years of its own fitting window has not demonstrated it works
now — only that it worked once.


## Done — 2026-09-09

`arena.recency(final_fold)` is the ninth term, in the same geometric mean as the
other eight and holding the same veto.

**The shape.** Zero at or below zero, full marks at `RECENT_FULL_MARKS = 0.20`,
linear between — a ramp, so a mutation that moves the final fold from 0.02 to
0.06 is rewarded for it. A step would have made everything under the floor
equally dead and given the search a cliff instead of a gradient.

**The one judgement call, and the argument for it.** An unjudgeable final fold
(`None`, under ten trades in 2024-2025) scores 1.0 and abstains rather than
failing. Scoring it zero would repeat a mistake this arena has already made
twice: unjudgeable folds once put the incumbent floor at zero, and a
training-side frequency proxy once punished selectivity and promoted genomes
taking four trades in the sealed window. The dodge a reader will reach for —
avoid the veto by not trading recently — is closed by `judgeable`, which already
demands fifteen trades in 2026, a window that sits *after* this fold.

**What the tests pin.** That a genome losing money in the last fold is vetoed
outright; that the ramp is monotone and saturates; that `None` abstains; and the
one that states the whole point — `consistency([0.4, 0.4, 0.4, 0.0])` and
`consistency([0.0, 0.4, 0.4, 0.4])` are *equal*, and `recency` separates them.
Three good folds out of four is 0.75 whichever three they are, and for all six
promoted systems the bad one was the most recent.

**The archive was retired, not migrated.** 237 rows scored under the eight-term
objective moved to `archive.8-term.retired.jsonl`, and the champion with them. A
surrogate fitted across both would learn the average of two different questions.
The arena re-derives its floor from `INCUMBENT_SIGNAL` in about two seconds and
the surrogate's memory rebuilds in ten minutes of searching, so this costs
almost nothing — and keeping the rows would have cost correctness.

**Still a bet, and still stated as one.** If the 2025 decline is noise rather
than decay, this discards systems that would have recovered.
