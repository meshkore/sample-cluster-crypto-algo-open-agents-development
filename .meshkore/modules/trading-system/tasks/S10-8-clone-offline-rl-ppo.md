---
id: S10-8
title: "F. Training: behaviour cloning, then offline RL, then PPO - each gated on validation years"
status: backlog
priority: high
owner: unassigned
profile: developer
category: trading-system
initiative: system-ten-conditioned-rl
created: 2026-09-27
updated: 2026-09-27
tags: [system10, training, rl, gpu, phase-f]
depends_on: [S10-7]
blocks: [S10-9, S10-10]
---

> Read `.meshkore/context/system10-design.md` before starting. It is the plan this task is one piece of, and it carries
> the laboratory's standing rules under "Our conditions" and the kill conditions under section 7.

## The ask

Train the policy in the order the design fixes, with a gate between each step, walk-forward
by year, four seeds, the spread reported. *"I hope there's intelligence in each iteration"*:
each step exists to answer one question and is recorded whichever way it answers.

## What to build

`system010_conditioned_rl/policy.py` and `train.py`:

1. **Clone.** The champion net's conviction mapped to the action set inside R is the
   baseline. Score it on every validation year with `autoloop._consistency` and
   `tools/quality.py`. This number is what everything after must beat.
2. **Offline RL.** Log transitions from the environment under the clone plus perturbations
   (epsilon-greedy over the action set) on years up to N-1; fit CQL or IQL (the dossier's
   choice) per walk-forward year N; four seeds. Gate: beats the clone on validation years
   2024 AND 2025 on the consistency score with worst-year Q not worse. If not, stop here
   and record it.
3. **PPO** in the environment, warm-started from step 2, only if step 2 passed its gate.
   Same seeds, same gate.
4. **Action-vote ensemble** of three or more seeds, only if the seed spread exceeds the edge.
5. Every run appends to `research/system10/rnd/program_progress.jsonl` in the same shape
   as 06's tape (id, seed, arm, score, min_year, cagr, annual, quality_worst, delta), and
   writes `research/system10/model_card.json` for the frontend.

Compute: brake 06's genome search (`research/system06/STOP_AUTOLOOP`) for the duration of
a GPU training and remove the brake after; never two trainings on the card. The live trader
and the pusher are never stopped.

## Done when

The clone baseline, the offline-RL result and (if reached) the PPO result are tabled per
validation year per seed with spreads; each gate's verdict is a row in *What helped* or
*What hurt*; the model card is published.
