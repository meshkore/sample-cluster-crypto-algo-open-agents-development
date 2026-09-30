# System 10 — results

**Nothing has been measured. This file exists so that the first number written into it has
a labelled place to go, and so that an empty record cannot be mistaken for a quiet one.**

Two eras, always labelled, as the standard requires.

## Training / research — every year strictly before 2026

| year | return | max drawdown | Q | trades | avg trade size |
|---|---|---|---|---|---|
| 2018 | — | — | — | — | — |
| 2019 | — | — | — | — | — |
| 2020 | — | — | — | — | — |
| 2021 | — | — | — | — | — |
| 2022 | — | — | — | — | — |
| 2023 | — | — | — | — | — |
| 2024 | — | — | — | — | — |
| 2025 | — | — | — | — | — |

Walk-forward exams (S10-10), four seeds each, the spread reported rather than the mean:

| exam | trained on | judged on | score | worst year | Q | ratio vs 06 |
|---|---|---|---|---|---|---|
| 1 | ≤ 2023 | 2024 | — | — | — | — |
| 2 | ≤ 2024 | 2025 | — | — | — | — |

## S10-6 — where the best trades live (2026-09-30)

`research/system10/tools/conditions.py` → `rnd/conditions_q{20,30,50}_2026-09-30.json`.
Walk-forward: for each year N the region is fitted on years < N and read on N. The book is a
naive one on purpose - three slots, a third each, enter wherever the region holds, leave by
06's stop + trail or after 384 bars (four days), no model anywhere, costs charged - so it
measures what the region is worth **before** a policy exists.

Pooled out-of-sample years 2019-2025, top 20% of the oracle's swings (30% and 50% agree):

| entries allowed | bars used | best swings inside | worst year | worst drawdown | P(year >= +20%) | p05 |
|---|---|---|---|---|---|---|
| everywhere | 100% | 99% | -84.3% | 86% | 60% | -61% |
| 06's gates (in-sample reference) | 10% | 36% | -73.3% | 75% | 67% | -53% |
| R 60% | 10% | 64% | -87.6% | 90% | 45% | -76% |
| **R 80%** | **14%** | **79%** | **-87.6%** | **90%** | **40%** | **-78%** |
| R 90% | 21% | 89% | -76.1% | 81% | 43% | -76% |

**What it says.** The operator's premise holds on width: the conditions that hold 80% of the
best swings occupy about 14% of the tape (not 3%), so a book could deploy there. It fails on
edge: **being inside the region is worse than entering anywhere** (P 40% against 60%). The
region is a volatility detector - wide bands, high ATR, price below its 55-bar high - and the
worst trades live in exactly the same conditions as the best. The design's feasibility gate
(`P(year >= +20%) >= 50%` inside R) is **not met**: kill condition 2 of section 7.

**What it does not say.** It does not test a policy inside R; the naive book has no trend or
regime brake, which is why 2022 costs ~85% in every variant. The first run of this tool used
06's band exit on the live net's probability and printed +3,313% for 2018 - a leak (that net
trained on those years), withdrawn and replaced by the model-free exit above.

## Sealed forward — 2026, read once, on the operator's word

**Not spent.** The reading is booked only if both exams pass and the per-year ratio spread
against system 06 does not straddle 1.0 (S10-10), and it is read exactly once (S10-11).

| | return | max drawdown | Q | trades | avg trade size |
|---|---|---|---|---|---|
| system 10 — maximum profit | — | — | — | — | — |
| system 10 — optimal on Q | — | — | — | — | — |
| system 06 (incumbent) | **+25.71%** | 22.1% | 0.2987 | 90 | — |
| system 06 — optimal on Q | +20.39% | 12.9% | 0.3233 | — | — |
| buy and hold | — | — | — | — | — |

## Champion configuration

None. The brain abstains until a policy is exported; `parameters()["trained"]` is `false`.

## The baselines this system is measured against

- **System 06 sealed 2026: +25.71% @ 22.1% drawdown** — the incumbent and the live engine.
- **System 02 sealed 2026: +5.05% @ 7.88%** — the bar the laboratory spent a month beating.
- **Behaviour cloning of 06 inside the region** — 010's own internal baseline, and the one
  that decides whether anything after step 1 of the training order is run at all.
