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

## S10-6b — the simplest conditions that pay (2026-09-30)

The operator asked for "a minimum list of conditions... as simple as possible". Eight
one-line combinations, round thresholds fixed before the run, same model-free book; chosen
on 2019-2023, then read on 2024-2025 (`rnd/simple_conditions_2026-09-30.json`).
T = slow trend up, B = at least half the universe in an uptrend, P = 3% below the 55-bar
high, V = 14-bar NATR above 1%.

| condition | bars | 2019-23 worst year | 2019-23 P(>= +20%) | 2024 | 2025 |
|---|---|---|---|---|---|
| everywhere | 100% | -84.3% | 64% | +44.6% / dd 44% | -36.1% / dd 56% |
| B | 48% | -40.2% | 79% | +26.5% / 39% | +18.9% / 23% |
| T&B | 39% | -39.7% | 78% | +18.6% / 41% | +7.8% / 25% |
| **T&B&P (chosen)** | **13%** | **-40.4%** | **85%** | **+20.1% / 54%** | **+2.9% / 46%** |
| T&B&V | 9% | -14.1% | 84% | +0.0% / 62% | +17.4% / 43% |

Every simple condition clears the feasibility gate the learned region failed (78-85%
against 40%), and the chosen one stays positive in both years it was not chosen on. The
edge is the market-wide one - breadth - not the coin's own shape. What no condition fixes
is the drawdown: 40-60% on a fully deployed, unmanaged book. That is the policy's job.

## S10-8a — per-bar PPO inside the region: from churn to silence (2026-10-01)

Exam 2024 (region and policy fitted on <= 2022, readings on 2023), two seeds, keep/switch
actions, reward = profit after costs - drawdown increase. Every reading on the three-slot book:

| update | seed 77101 (2023) | seed 91002 (2023) |
|---|---|---|
| 50 | -98.6%, 4,595 trades | -95.1%, 3,656 trades |
| 100 | -36.7%, dd 41%, 681 trades | -24.9%, dd 29%, 344 trades |
| 150 | -8.8%, dd 14%, 79 trades | +2.1%, dd 5%, 21 trades |
| 200-300 | 0 trades | 0 trades |

The policy learns one thing well - that trading costs money - and walks monotonically from
churn to abstention. No checkpoint that trades is profitable. With a decision every 15
minutes the per-bar reward is noise around the toll, and the S10-6 finding (the region by
itself has no edge) leaves nothing else for it to find. Stopped after the first exam; the
remaining seeds and exam 2025 would repeat it. A first run on flat/long actions collapsed
the same way faster, and a run scored by argmax read zero trades from an active policy -
both fixed before this one and recorded in the commits.

## S10-8b — one decision per trade inside the region (2026-10-01)

A scorer (MLP, Huber) predicts each in-region opportunity's criterion - net after costs minus
lambda x the trade's worst excursion - and takes those above a bar chosen on the selection
year (best Q among bars trading >= 100 times). Fixed causal exit. Four seeds per arm.
`rnd/bandit_exams_2026-09-30.json`, `rnd/bandit_exams_market_2026-09-30.json`.

| arm | exam 2024 (chosen on 2023) | exam 2025 (chosen on 2024) |
|---|---|---|
| take everything in the region | -1.4% / dd 78% | +1.2% / dd 54% |
| scorer, lambda 1 | 4/4 positive: +15.7% to +268.8% | **4/4 negative: -42.9% to -78.3%** |
| scorer, lambda 0 (max profit) | 2/4 positive, dd 51-79% | 1/4 at +0.2%, rest -25% to -60% |
| scorer + market state, lambda 1 | 3/4 positive, +115% to +361% | 3/4 negative (-47.7% to -84.5%), one +1.2% |
| scorer + market state, lambda 0 | 4/4 positive | 4/4 negative (-55.5% to -76.1%) |
| *for scale: breadth >= 50% alone (S10-6b)* | *+26.5% / dd 39%* | *+18.9% / dd 23%* |

**Verdict: refused.** The scorer learns which trades paid in the years it saw, and those years
are bull-dominated: it selects the highest-beta entries, which is spectacular in 2024 and
ruinous in 2025. The spread across seeds (+16% to +361% in one year) is wider than any edge.
Giving it the market's state did not change the 2025 answer. Per section 7, no sealed or
forward claim is made from this; the continuous trainer stays braked.

The one construction that stayed positive in both unseen years today is the simplest one:
half the universe in an uptrend (S10-6b).

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
