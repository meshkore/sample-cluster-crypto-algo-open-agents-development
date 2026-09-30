---
id: S10-3
title: "B. Design dossier: argue every default of the RL design from the published record"
status: blocked
priority: high
owner: unassigned
profile: consultant
category: trading-system
initiative: system-ten-conditioned-rl
created: 2026-09-27
updated: 2026-09-30
tags: [system10, design, literature, phase-b]
depends_on: []
blocks: [S10-7]
---

> Read `.meshkore/context/system10-design.md` before starting. It is the plan this task is one piece of, and it carries
> the laboratory's standing rules under "Our conditions" and the kill conditions under section 7.

## The ask

The code gate (`.meshkore/context/constraints.md`): the design is examined to
state-of-the-art quality through the published record before a policy is trained. This task
runs in parallel with S10-1/S10-2 and must be **agreed by the operator** before S10-7 starts.

## What to produce

`research/system10/DESIGN_DOSSIER.md`, in English, one section per default in the design's
section 4 - state, actions, reward, episodes, algorithm order, region, validation, compute -
and for each: what the reading list (section 8) supports, what it contradicts, and what the
design does about the contradiction. Claims are cited to the source; nothing is paraphrased
from memory. Add sources to `research/system10/knowledge/sources.jsonl` in the same shape as
`research/system06/knowledge/sources.jsonl`.

Three questions the dossier must answer explicitly, because the laboratory's own record
bears on them:

1. **Offline before on-policy.** One price history is one trajectory. What does the offline
   RL literature (CQL, IQL, Decision Transformer) say about learning from a fixed dataset
   without exploring it, and what do the FinRL contest reports say fails out of sample?
2. **Reward shaping with drawdown.** Moody & Saffell's differential Sharpe against a
   per-bar drawdown penalty against a terminal Q: which has published evidence of
   surviving costs, and at what lambda range?
3. **Ensembles over actions, not probabilities.** A43/P22 lost by averaging probabilities;
   2501.10709 wins by voting over actions. State the aggregation rule 010 will use and why.

No scripts, no measurements, no numbers of our own in this task. The repository is read for
one reason: not to re-propose something already closed (`experiment-catalogue.md`,
`research/system06/IDEAS.md`).

## Done when

The dossier exists, every section-4 default is either confirmed with a citation or replaced
with one, the operator has read it and said the design is agreed, and the design document's
section 4 is updated to the agreed defaults in the same commit.
