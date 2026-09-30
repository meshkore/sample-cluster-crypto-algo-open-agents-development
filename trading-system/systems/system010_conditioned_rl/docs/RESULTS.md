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
