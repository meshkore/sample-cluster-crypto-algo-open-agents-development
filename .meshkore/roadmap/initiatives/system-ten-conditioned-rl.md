---
id: system-ten-conditioned-rl
title: "System 10: a reinforcement-learning policy trained only where the best trades live"
status: active
priority: high
oneliner: "Locate the causal conditions under which 80% of the oracle's best trades occur, then train a policy by reinforcement learning inside that region only, rewarded by the operator's profit-against-drawdown criterion, walk-forward by year, and take it live through the engine swap - in the operator's order: cleanup, new system, data, frontend, conditions, training, testing, forward."
modules: [trading-system]
target: "two walk-forward exams passed 2-of-2 against system 06 with the odds priced, one sealed 2026 reading, and an engine package v4-rl in shadow paper trading"
created: 2026-09-27
updated: 2026-09-27
owner: unassigned
related: [system-eight-from-zero, system-nine-reality-alignment]
---

## Why this initiative exists

The operator asked on 2026-09-27 whether any of the laboratory's systems had used
reinforcement learning directly. None had: 001-009 learn by rule search, supervised labels,
meta-labelling, behaviour cloning of a hindsight oracle, or not at all. The one RL-shaped
item, `A53-regime-conditional-labels`, was proposed and never built.

His design is specific and it is the right shape for this laboratory's record: *do not
apply the learner to the whole chart; find the conditions under which the best trades
happened, and train it there.* The champion's own ledgers say why that matters - the same
entries return +30.86% a trade under the hindsight exit and +0.44% under the rule the engine
runs (`tools/exits.py`), and every cohort the gates refused in the sealed year was negative
(`tools/refusals.py`). The prize is inside a region; the gates are its first draft.

The full plan, with the defaults, the reasons, the kill conditions and the reading list, is
`.meshkore/context/system10-design.md`. **Read it before taking any task.**

## Scope

- **In:** cleanup of the laboratory before opening 010; the `system010_conditioned_rl`
  package and its `research/system10/` runtime; a data audit with the 2026 seal verified;
  the frontend showing 010 as a box with a model card; the region learner and its coverage
  report with the feasibility bootstrap inside the region; an environment over the frozen
  backtester's ledger; behaviour cloning → offline RL → PPO, each gated on validation;
  training daemons under the watchdog with their own brake; two walk-forward exams; one
  sealed reading; an engine package in shadow paper trading beside 06.
- **Out:** touching `backtester/`, `research/system06/` or the live book; online learning
  on live prices; any venue broker; any 2026 bar outside the sealed reading and the trader.

## The order, which is the operator's

| Phase | Tasks |
|---|---|
| Gate 0 - the operator says GO | - |
| A. Cleanup | S10-1 |
| B. New system | S10-2 (skeleton), S10-3 (design dossier from the published record; agreed by the operator before training) |
| C. Data | S10-4 |
| D. Frontend | S10-5 |
| E. Conditions | S10-6 |
| F. Training | S10-7 (environment), S10-8 (clone → offline RL → PPO), S10-9 (daemons) |
| G. Testing | S10-10 |
| H. Forward | S10-11 (sealed reading, on the operator's word), S10-12 (engine package, shadow book) |

## Done looks like

- `trading-system/systems/README.md` carries row 010 with a sealed 2026 figure and a
  verdict, and `docs/SUMMARY.md` has a *What hurt* table at least as long as *What helped*.
- The dashboard shows 010 in the systems list, its formation as a model card, and - if it
  reached H - its shadow book in the Trading area beside 06.
- Both numbers on record for 010: the maximum-profit configuration and the optimal one.
- Every kill condition in the design's §7 either did not fire or is recorded as the reason
  the initiative stopped where it stopped.

## How this initiative ends

Either an engine package `v4-rl-<name>` is live on the operator's word, or the initiative
stops at a named kill condition with the finding written into 010's summary. It never ends
by fading out.
