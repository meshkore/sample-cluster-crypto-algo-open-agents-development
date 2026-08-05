---
id: QUANT16
title: "Long-only profit inside a confirmed bear regime, and the 2026 forward test"
status: in_progress
priority: critical
owner: unassigned
category: quantlab
initiative: liquid-ml-research
created: 2026-08-05
updated: 2026-08-05
tags: [regime, bear, forward-test, selection, scope]
depends_on: [QUANT15]
blocks: []
---

## What was asked

The operator's read: 2026 is a bear market, the laboratory has no algorithm that
makes money in one, and the best 2026 result is about +3%. Work the bear branch
and the major-trend detector, train strictly on pre-2026 data, and produce a
2026 result far better than the incumbent.

## 2026, measured

| | 2026-01-01 → 2026-07-31 |
|---|---|
| BTCUSDT | **-28.2%** (max DD 39.5%) |
| ETHUSDT | -37.3% (53.3%) |
| BNBUSDT | -32.1% (42.4%) |
| SOLUSDT | -41.5% (57.6%) |
| XRPUSDT | -42.4% (55.7%) |
| median of 399 assets with full 2026 history | **-47.2%** |
| assets positive over 2026 | **40 of 399 (10.0%)** |

The operator's read is correct and then some.

## The detector called it

`regime.py` flipped to BEAR on **2025-12-21**, eleven days before the forward
window opens, and held BEAR for **100% of 2026** while the reference composite
fell 40.6%. The label is produced by the same causal code the prefix-equality
test covers, so this is not hindsight. Piece one of the four-piece system works
on the single most valuable call it will ever make.

## The hypothesis that looked right and was wrong

40 of 399 assets rose, several above +100% (+361%, +155%, +146%, +142%). That
reads as an argument for cross-sectional selection: pick the strong ones. It is
wrong, and the measurement is unambiguous. Ranking the liquid universe by
trailing 30-day return inside pre-2026 BEAR regimes, mean forward 7-day return
by decile:

| decile | BEAR | SIDEWAYS | BULL |
|---|---|---|---|
| 0 (strongest) | -1.66% | +0.88% | -0.55% |
| 9 (weakest) | -1.52% | +2.48% | -1.98% |
| **spread** | **-0.13%** | -1.60% | +1.43% |

**Every decile is negative in a bear regime and the spread is nil.** The 2026
winners are identifiable in hindsight and not by momentum rank in advance —
reasoning from that top-40 list was survivorship reasoning pointed forward.
Cross-sectional momentum is rejected as the bear mechanism.

## What does work: absolute strength, not relative

Pre-2026, inside BEAR regimes, liquid assets, mean forward return:

| condition | 7d | 30d | n |
|---|---|---|---|
| every liquid asset | -1.10% | **-5.41%** | 20,636 |
| 90-day momentum positive | -1.21% | -1.56% | 6,080 |
| above own 200-day average | +0.43% | +2.50% | 4,467 |
| **above own 200d AND 50d** | **+0.80%** | **+3.13%** | 3,988 |

An 8.5-point swing against the bear baseline. Being *up over 90 days* is not
enough and is negative; being above both averages is what pays. `bear_short=`
alone (above the 50-day only) is -3.55% at 30d, so the conjunction is
load-bearing and is pinned by its own test.

`_BearParticipationBranch` was rebuilt on exactly this condition, and the
router's scope moved from five hourly majors to the **wide daily universe**,
because this branch needs breadth: in a bear market only a handful of names out
of hundreds qualify, and on five majors that all fell 28-42% together the
correct answer is "hold nothing".

## Selection, pre-2026 only

Ledger: 13 cells (one dial at a time) + 6 (bracketing the bull pair after its
first winner landed on a range edge) + 8 (other dials, bull pinned) + 1
combination + 8 at the corrected scope = **36 pre-2026 cells, one forward
evaluation of the winner.**

The bull pair mattered most and for a diagnosable reason: it had inherited
H-SMARSI-001's 50/200 parameters, which were fitted on **hourly** bars. On daily
bars 50/200 is so slow the branch barely trades (81 trades, 1.8% exposure). The
bracketed curve has an interior peak:

| bull pair | return | max DD |
|---|---|---|
| 8/21 | +78.74% | 27.22% |
| **10/30** | **+1179.14%** | 24.74% |
| 15/40 | +912.95% | **30.15% ABORTED** |
| 20/50 | +996.69% | 24.65% |
| 25/65 | +656.51% | 25.61% |
| 30/80 | +9.43% | 27.27% |

Interior peak, so not a boundary artifact — but 15/40 aborting between two legal
neighbours says the surface is rough and the winner carries luck.

## A selection error the pipeline caught, and the bug under it

The first selection ran on 321 assets, because it filtered for ≥260 bars and
silently dropped 65 newer listings. The real universe is 386. **The winner
chosen on the subset aborted at the true scope**, and S00852's first Phase-1 run
is on record as `ABORTED_DRAWDOWN` at 31.35%. That is the deployment-scope
decision biting its own author: "roughly the same universe" is not the scope.

Re-running at the true scope exposed a second, worse problem. The two evaluators
rebuilt stored policies from **hand-maintained key lists**, one per module, and
`drawdown_deleverage_end` had been added to `MoneyManagement` and to neither
list. Both phases silently dropped it, it fell back to `maximum_drawdown` — just
raised to 0.30 — and the de-leverage ramp widened without anyone asking: average
exposure 18.7% instead of 8.1%, and a configuration measured legal at 24.72%
aborted at 31.35%. `forward.py`'s copy was additionally missing
`minimum_position_fraction` outright, so every forward run since that field
existed used the dataclass default instead of the stored one.

Fixed by deriving the list from the dataclass (`portfolio.policy_keys`), so a
new field is threaded through both phases the moment it exists, with a
regression test asserting the two sets are equal.

## Result: S00852

| | Phase 1 (pre-2026, 386-asset daily) | Forward 2026 |
|---|---|---|
| return | **+1480.02%** | **-0.80%** |
| max drawdown | 24.72% (legal) | **6.60%** |
| trades | 941 (60 assets traded) | 78 |
| average exposure | 8.08% | 16.05% |
| control, same scope | +23.77%, **30.01% ABORTED** | — |
| excess over control | **+1456 points, at 5.3 points LESS drawdown** | — |

Walk-forward: 7 of 12 folds profitable, consistency 0.583 — but **not eligible**,
because it breached the drawdown stop in 1 of 12 folds. That is the instrument
doing its job and it is a real mark against this configuration.

## Did it meet the goal? No.

The target was to beat the incumbent best 2026 result of +4.33%. This returns
**-0.80%**. Stated plainly: not achieved.

What it did do: -0.80% against a median asset of -47.2%, with a 6.60% drawdown
in a year whose majors drew down 39-58%. That is roughly 46 points of alpha and
near-total capital preservation, and it is the best Phase-1 result the laboratory
has ever produced by an order of magnitude — legal where the control aborts.

**And the target itself deserves scrutiny.** The incumbent +4.33% is the maximum
of **313 forward runs** whose median is -1.47% and of which only 14 (4.5%) are
positive. The top three are all `volume_climax` with ~44 trades and near-zero
exposure — strategies that returned +4% by barely participating in a -47% market.
A maximum drawn from 313 trials, when the median is negative and the winner
barely traded, is what multiple testing produces. Chasing that number by
iterating against 2026 would manufacture exactly the same artifact and destroy
the only untouched evidence this laboratory has.

## The structural constraint, stated

Long-only, in a market where the median asset falls 47%, the reachable outcomes
are: hold cash and return ~0%, or find genuine absolute strength. There is no
third option without shorts or inverse instruments, which the charter forbids
and should keep forbidding. So in a bear year the honest objective is capital
preservation plus alpha, and "large positive absolute return" may simply not be
available to this mandate. That should be argued about explicitly rather than
pursued by tuning.

## Deliberately not done

- **No tuning against 2026.** One forward evaluation, reported as run. Setting
  `bear_weight=0` would plausibly improve the 2026 number toward zero, and
  pre-2026 evidence points the other way (0.6 beat 0.3 and 1.0), so making that
  change now would be fitting the forward window.
- **No neural network.** Asked for, and declined for now on sequencing: the
  cycle sample is 2-3 tops and bottoms, a model with more parameters than that
  has nothing to learn from, and the last two rounds found two measurement bugs
  in the existing instrument. A model fitted through a defective instrument
  produces confident nonsense. The honest prerequisite is the walk-forward
  eligibility failure above.

## Acceptance criteria

- Detector labels remain causal; 2026 never influences selection.
- Every abort reported as a disqualification, never dropped.
- The selection ledger states how many cells were tried and how many forward
  evaluations were spent.
- The goal is reported as met or unmet, plainly.
