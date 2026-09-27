---
title: "System 10 - the conditioned policy: reinforcement learning inside the region where the best trades live"
category: context
updated: 2026-09-27
owner: master
status: initiative prepared; execution starts on the operator's word
---

# System 10 - the conditioned policy

**One sentence.** The best trades in this market do not happen everywhere; they cluster
under a small set of causal conditions. System 10 first *locates* that region from the
oracle's own best trades, and then trains a policy by reinforcement learning **only inside
it**, rewarded by the operator's criterion (profit against drawdown, after costs), so that
every hour of the card is spent where the prize is and none where it is not.

Slot: `trading-system/systems/system010_conditioned_rl/`. Runtime: `research/system10/`.
Initiative: `.meshkore/roadmap/initiatives/system-ten-conditioned-rl.md`. Tasks `S10-1`
to `S10-12`.

> **This document is the plan.** It is written so that an agent who has never seen this
> laboratory can execute it task by task. Every choice below is a default with a reason,
> not a decree: S10-3 exists precisely to argue the defaults against the published record
> before any of them is trained. What is *not* a default is the set of rules under
> "Our conditions" - those are the laboratory's, and they do not move.

---

## 0. The operator's ask, and the two corrections to the premise

Operator, 2026-09-27 (translated): *"Reinforcement learning is a system that learns
continuously and, with all the data available, performs the best trades. We already know
the maximum potential of a chart - if we got every entry and exit right. An RL system could
on its own read the charts and the indicators and decide where to buy and sell, getting
closer each time to a higher profit... Instead of applying it to the whole chart, to every
candle, to every moment of history, apply it only in the places and above all the
CONDITIONS in which 80% of the best trades have occurred... Do not tell me the ideal
conditions are 3% of the time; the window has to be wide enough to train and to execute."*

Two corrections, both of which make the idea stronger rather than weaker:

**1. "Continuously learning" cannot mean learning on the live tape.** In this laboratory
2026 is a sealed window and a reading is spent, never repeated. A policy that updates
itself on 2026 bars is training on the exam. What *is* allowed, and is the honest form of
"continuous": walk-forward learning - the policy is retrained on everything up to the end
of year N and judged on year N+1, for every N, so that its record is a sequence of
out-of-sample years rather than one fit. In production the same mechanism is a scheduled
retrain on closed years, promoted through the live engine swap, never an online update.

**2. "The maximum potential of the chart" already exists here, and it is the teacher.**
System 06's zigzag oracle marks, with hindsight, every clean up-swing above the cost floor;
`research/system06/tools/exits.py` prices it: the same 297,730 entries return **+30.86% a
trade under the hindsight exit and +0.44% under the rule the engine actually runs**. That
gap is the prize System 10 is aimed at, and it is measured, not imagined. The oracle also
answers the operator's *"3 maximum, minimum... 1% profit"*: its threshold is the cost floor
(`threshold: 0.03` in the champion's config), and it is a parameter of the teacher, not of
the student.

And one clarification of the operator's worry: **conditioning is a coverage-for-variance
trade, and the coverage number is a deliverable, not a hope.** S10-6 reports what fraction
of research bars the region covers, per year, and the feasibility bootstrap is run *inside
the region*. If the region that holds 80% of the best trades covers 3% of the tape, that is
reported as a finding and the region is widened until a three-slot book can actually deploy
in it - the width is chosen by that arithmetic, in the open.

---

## 1. Has this laboratory used reinforcement learning before? No.

Read before opening 010, per the documentation standard: `trading-system/systems/README.md`
and every `docs/SUMMARY.md`. The learning methods used so far:

| System | How it learns | Relation to 010 |
|---|---|---|
| 001 rule grammar · 002 intraday hypotheses · 007 dip-buyer · 008 residual momentum | Fixed rules; 008's rules come from published papers | none |
| 003 supervised ML | Triple-barrier labels, purged splits; became `quantlab_ml/` | 010 reuses its purged-split discipline |
| 004 LLM-written rules | A seat writes → measures → rewrites | none (its lesson: training return does not rank forward return) |
| 005 meta-labelling | A supervised classifier that vetoes entries | 010's gates inherit it through 06 |
| **006 oracle-taught net (champion, live)** | **Behaviour cloning of a hindsight oracle** + a fixed decision tree | **010's warm start and its feature set** |
| 009 participant ledger | Agent-based simulation, no learner | none |

The only RL-shaped item on record is `A53-regime-conditional-labels` in
`research/system06/rnd/agenda.jsonl` - *proposed, never built* - which cites the 2026 MDPI
paper on market-conditional reward functions already in
`research/system06/knowledge/sources.jsonl`. System 10 is A53 taken seriously.

Two refusals on record that constrain 010's design and must not be re-run:

- **Bagging identical nets loses** (A43, A48, P22: bag 3 nets −0.1587). The reason is
  recorded: averaging *probabilities* pulls convictions off the extremes the book trades.
  So a 010 ensemble, if any, votes over **actions** from differently-trained policies (the
  FinRL contest finding recorded in the knowledge base *because* it disagreed with ours),
  never averages scores.
- **Turnover levers fitted on the full record describe a dead market** (06 rule 6; A128
  closed 2026-09-18: `min_hold` 1 wins 2018-2021 16/16 and 2022-2025 9/16). So 010's
  validation years are the modern ones and every per-year table is read with 2021 set
  aside, exactly as the Q criterion already does (`quality_worst`, not the 2021-dominated
  mean).

---

## 2. What 010 reuses, unchanged, and why that is the whole point

The build is small because the laboratory has already paid for the expensive parts:

| Reused | From | Used as |
|---|---|---|
| 44 causal features per bar, 96-bar windows, 14 pooled USDT pairs at 15m | `system006_oracle_net_15m.dataset` / `channels` | the policy's **state** |
| The zigzag oracle and its cost-floor threshold | `system006_oracle_net_15m.oracle` | the **teacher** for the region and for the warm start |
| The champion net's conviction channel | `engines/v3-exit-010` | a state feature *and* the behaviour-cloning warm start |
| The gates: trend, breadth, meta, fear | `modules/` | the **first draft of the region** R, already priced by `tools/refusals.py` |
| The frozen backtester's accounting: next-bar fills, 10 bps + 5 bps, √participation impact | `backtester/` | the **environment's** ledger - 010 calls it, never re-implements it |
| Per-calendar-year $100,000 accounts, the consistency score, the Q criterion | `autoloop._consistency`, `tools/quality.py` | the **reward** and the **ranking** |
| The paired A/B runner with seeds, controls and the progress tape | `research/system06/autotest.py` | the **experiment discipline** (a 010 copy under `research/system10/`) |
| The live layer: paper broker at the real spread, engine packages, hot swap | `live-trading/` | how 010 **goes live** without touching the book |

A layering rule follows: `system010` may import `quantlab_core`, `quantlab_catalog`,
`quantlab_ml`, `quantlab_backtester` and - as a **declared lineage** in
`orchestrator-manager/scripts/check_layering.py` - `system006_oracle_net_15m` for its
dataset, oracle and channel builders. It imports nothing from `live-trading/` (a leaf) and
never writes into `research/system06/`.

---

## 3. The architecture

```
                 15m candles, 14 pairs, catalogue (research <= 2025-12-31 | sealed 2026)
                                          |
                          system006 dataset -> 44 causal features / bar
                                          |
              +---------------------------+---------------------------+
              |                                                       |
     ZIGZAG ORACLE (hindsight, research only)               CAUSAL CHANNELS (prob, trend,
     marks every clean up-swing above the cost floor        breadth, meta, fear, vol, ...)
              |                                                       |
     "the best trades" = top of the oracle's swings                   |
              |                                                       |
     S10-6  REGION LEARNER  ------------------------------->  R(t) in {0,1}   causal predicate,
            which causal conditions hold on 80% of them        |               fitted <= year N-1
            (coverage per year reported, feasibility            |
             bootstrap run INSIDE the region)                   |
                                                               v
                                             +------------------------------------+
                                             |  POLICY  pi(a | s)   S10-7 / S10-8  |
                                             |  consulted only where R(t) = 1      |
                                             |  outside R: abstain / manage exits  |
                                             |  s = features + book state + regime |
                                             |  a = {enter x size, hold, exit}     |
                                             |  warm start: clone the oracle (=06) |
                                             |  then offline RL, then PPO if it    |
                                             |  beats the clone on validation      |
                                             +------------------------------------+
                                                               |
                                             ENVIRONMENT = the frozen backtester's ledger
                                             episode = one calendar year, $100,000
                                             reward  = d(log equity) - lambda * d(drawdown) - costs
                                             terminal = Q(year) = return^2 / max(dd, 2%)
                                                               |
                                 walk-forward: train <= N-1, validate N, 4 seeds, spread reported
                                                               |
                                 exams 2024 and 2025 (2-of-2) -> price the odds -> sealed 2026 ONCE
                                                               |
                                 engine package v4-rl-<name> -> live-trading hot swap, paper book
```

**Where the intelligence is, in one line each.** The *region* is learned from the teacher's
best trades (what the operator asked for). The *policy* is learned by reward, inside the
region, with the book's state in front of it - which is the one thing the 06 net never sees
and the reason its per-entry edge is unharvestable by a three-slot book (P59: hold 384 wins
per entry, loses in the book). The *reward* is the operator's criterion, so the policy is
optimising the thing it will be judged on rather than a proxy.

---

## 4. Default design choices - to be argued in S10-3, then frozen

Each default has a reason; S10-3 replaces any of them only with a citation.

**State.** The 06 feature window (44 × 96) plus **book state**: position flag, unrealised
return, bars held, slots free, distance from the year's equity peak, and the regime cluster
id from the region learner. Book state is the addition that makes this RL rather than
classification - the same market bar is a different decision with a full book.

**Actions.** Discrete and small: `{abstain, enter half-slot, enter full-slot, hold, exit}`.
Long-only spot. A small action space is a choice against variance: the laboratory's own
record says every lever it has ever added beyond nine has failed to earn its place.

**Reward.** Per bar, the change in log equity minus λ times the increase in drawdown from
the year's peak, minus the round trip and impact charged by the backtester. Terminal reward
at year end: the Q criterion `sign(r)·r² / max(dd, 0.02)`. λ is a lever *of the reward*, not
of the policy, and it is the lever that puts the operator's *"monetary safety is a
priority"* into the objective directly.

**Episodes.** One calendar year with a fresh $100,000, so that the policy is trained on
exactly the unit the consistency law scores. Years are sampled with 2021 down-weighted, for
the reason the Q criterion ranks on the worst year.

**Algorithm, in this order and with a gate between each.**
1. **Behaviour cloning** from the oracle = the champion net, already trained. This is the
   baseline every later step must beat *on validation years*, not on training years.
2. **Offline RL** (conservative Q-learning or implicit Q-learning) on transitions replayed
   from the backtester under the cloned policy plus perturbations. Offline first because
   the market is **one trajectory**: an on-policy learner exploring a single history
   memorises it (the failure that killed six systems here), and conservative methods are
   built to stay near the data.
3. **On-policy fine-tune (PPO)** in the environment, only if step 2 beat step 1 on two
   validation years. If it does not, the plan ends at step 2 and says so.
4. **Ensemble over actions** (majority vote of ≥3 differently-seeded policies), only if a
   single policy's seed spread is wider than its edge. Never probability averaging (§1).

**Region.** A causal predicate over the same features, fitted on years ≤ N−1: a shallow
tree or a small set of thresholds that covers ≥80% of the oracle's top-quantile swings.
Interpretability is a requirement, not a preference - the region is what the operator
asked to *see*, and the refusal ledger must be able to price what it excludes. The current
gates are the zero-th version of R and the first thing S10-6 measures against.

**Validation.** Purged walk-forward by year with a 96-bar embargo; **four seeds**; report the
fold spread and the worst year, never the mean; select on validation years, never on 2026.

**Compute.** RTX 4060, 8 GB. One heavy training at a time (`RESOURCE_POLICY.md`). System 10
takes the GPU lane by braking 06's genome search (`research/system06/STOP_AUTOLOOP`) for the
duration of a training, and releases it after; the live trader and the pusher are never
stopped. The environment replay is CPU and runs in parallel.

---

## 5. Phases - the operator's order, with the work inside each

The operator named the order: *cleanup → generate the new system → clean the data →
synchronise with the frontend → then everything: the conditions, training, testing, forward
testing, all under our conditions.* Each phase below is one or more roadmap tasks; the task
files carry the "done when".

| Phase | Tasks | Gate to pass before the next phase |
|---|---|---|
| **Gate 0** | - | The operator says **GO** in words. Until then this is a prepared plan. |
| **A. Cleanup** | S10-1 | Three suites green, layering green, `LESSONS.md` regenerated, 06 confirmed champion + live and untouched. |
| **B. New system** | S10-2, S10-3 | Skeleton registered and documented; the design dossier argued from the published record and **agreed by the operator**. |
| **C. Data** | S10-4 | Data audit written; the 2026 seal verified physically; the feature registry frozen. |
| **D. Frontend** | S10-5 | 010 visible as a box; its training area shows a model card, not a curve; the pusher publishes it with no deploy. |
| **E. Conditions** | S10-6 | The region defined, its coverage per year reported, feasibility bootstrap inside it read against the target. |
| **F. Training** | S10-7, S10-8, S10-9 | Environment golden-tested against the backtester; clone → offline RL → PPO each gated on validation; training daemons under the watchdog with their own brake. |
| **G. Testing** | S10-10 | Two walk-forward exams (2024, 2025), 2-of-2, odds priced against 06 per year. |
| **H. Forward** | S10-11, S10-12 | Sealed 2026 read exactly once on the operator's word; engine package built; shadow paper book beside 06; swap only on the operator's word. |

---

## 6. Our conditions - the rules this plan runs under

These are the laboratory's standing rules, collected so that no task has to rediscover one.

- **Long-only spot** for 010's first version. Shorts were re-permitted as a *guide* on
  2026-09-08; 010 inherits 06's long-only lineage and adds a short action only as a later,
  measured lever.
- **Costs are real:** 10 bps commission, 5 bps slippage each way (0.30% round trip) in the
  backtester, plus √participation impact at 60 bps; the live paper broker measures the real
  spread instead of assuming it. Never weakened to rescue a result.
- **Research ends strictly at 2025-12-31. 2026 is sealed**, read once at an adoption, on
  the operator's word, after the odds are priced. No 010 process ever loads a 2026 bar
  except the sealed reading and the live trader.
- **Drawdown is an objective to minimise**, 25% is the mandate's boundary; the operator's
  criterion is Q = return² / drawdown, and **both numbers are always reported**: the
  maximum-profit configuration and the optimal one. Nothing is hidden for being negative.
- **Consistency law:** each calendar year an independent $100,000 account; score =
  worst year + 0.10·CAGR; positive every year is the bar.
- **Two walk-forward exams before any sealed reading; price the odds first** (per-year
  ratio spread against the incumbent must not straddle 1.0).
- **Seeds ≥ 4, spread reported, never a mean alone.** Selection on validation years only.
- **The backtester is never touched in a strategy change.** `backtester/` decides nothing.
- **Credentials outside the repository**, paper broker only, no venue broker reachable
  from a flag. Unchanged and absolute.
- **Documentation in the same commit as the result:** every adoption or refusal adds a row
  to `docs/SUMMARY.md` *What helped* or *What hurt*, and `context.json` with it.
- **English** everywhere in the repository; the operator's words translated and quoted.
- **One heavy training on the card at a time.**

---

## 7. What would stop this system - named before it starts

Each is a kill condition with an owner task, so the plan cannot drift past it.

| Condition | Where it is read | What happens |
|---|---|---|
| The region holding 80% of the best trades is too narrow for a three-slot book to deploy (coverage reported per year) | S10-6 | Widen R to the smallest region where the bootstrap passes, and report the 80% figure that was given up. If none passes, stop. |
| Feasibility bootstrap inside R: `P(year ≥ +20%) < 50%` on the *capturable* return (not the oracle cap) | S10-6 | Say so to the operator immediately; the target or the design changes before training. |
| Offline RL does not beat the behaviour-cloning baseline on two validation years | S10-8 | The plan ends at the clone; PPO is not run. Recorded under *What hurt*. |
| Seed spread wider than the edge after four seeds | S10-8 | Action-vote ensemble is tried once; if the spread survives, no exam is booked. |
| Per-year ratio spread against 06 straddles 1.0 in 2024 and 2025 | S10-10 | No sealed reading. The result is a research finding, not a candidate. |
| The sealed reading is negative or worse than 06 on Q | S10-11 | Published as measured. 06 stays live. 010's summary is finished honestly. |

---

## 8. Reading list for S10-3 - where the published record already speaks

Recorded here so the design phase starts from what other people have measured rather than
from what this box can compute. Claims from these are to be *read and cited*, not
paraphrased from memory.

- Moody & Saffell, *Learning to trade via direct reinforcement*, IEEE TNN 2001 - the origin
  of reward-as-trading-performance (differential Sharpe); the reason our reward is Q.
- Deng, Bao, Kong, Ren & Dai, *Deep direct reinforcement learning for financial signal
  representation and trading*, IEEE TNNLS 2017.
- Jiang, Xu & Liang, *A deep reinforcement learning framework for the financial portfolio
  management problem*, 2017 - crypto, portfolio vector, and the overfitting it reports.
- Zhang, Zohren & Roberts, *Deep reinforcement learning for trading*, J. Financial Data
  Science 2020 - discrete actions, volatility scaling, and what survives costs.
- Liu et al., *FinRL* (2020-2022) and the ICAIF FinRL contest reports - the benchmark
  environments and, more usefully, the published record of what fails out of sample.
- The ACM ICAIF ensemble paper already in `knowledge/sources.jsonl` (2501.10709) - voting
  over actions versus averaging outputs; recorded because it disagrees with A43/P22.
- The 2026 MDPI paper on market-conditional reward functions already in the knowledge base -
  the closest published form of "a different objective per regime".
- Kumar, Zhou, Tucker & Levine, *Conservative Q-Learning*, NeurIPS 2020; Kostrikov, Nair &
  Levine, *Implicit Q-Learning*, 2021; Chen et al., *Decision Transformer*, NeurIPS 2021 -
  learning from a fixed dataset without exploring it, which is what one price history is.
- López de Prado, *Advances in Financial Machine Learning*, ch. 3, 7, 11-14 - purging,
  embargo, the deflated Sharpe, and why the number of trials must be declared.
- Bailey, Borwein, López de Prado & Zhu, *Pseudo-mathematics and financial charlatanism*,
  2014 - the backtest-overfitting result every RL trading paper should be read against.

S10-3's deliverable is the dossier that says, for each default in §4, which of these
supports it, which contradicts it, and what the design does about the contradiction.

---

## 9. Where things live

```
trading-system/systems/system010_conditioned_rl/
    __init__.py          registers the brain (abstains until a policy is exported)
    region.py            the region learner and the causal predicate R(t)
    env.py               the environment over the frozen backtester's ledger
    policy.py            the policy network and the action head
    train.py             clone -> offline RL -> PPO, walk-forward, seeds
    export.py            writes an engine package for live-trading/engines/
    docs/                SUMMARY.md, RESULTS.md, context.json (the standard; three files)
research/system10/
    README.md            what is committed here and what is scratch
    DATA_AUDIT.md        S10-4's report
    rnd/                 agenda.jsonl, program.jsonl, progress tape, verdicts
    tools/               one-off measurements, each writes a dated JSON
    autotest.py          the paired-experiment runner (a 010 copy of 06's)
    STOP_S10             the brake the watchdog respects for 010's training
live-trading/engines/v4-rl-<name>/    only after S10-11, and only on the operator's word
```

---

## 10. What this initiative must NOT do

- It must not start training before the operator has agreed the S10-3 dossier.
- It must not touch `backtester/`, `research/system06/` or the live book.
- It must not load a 2026 bar anywhere except the sealed reading (S10-11) and the trader.
- It must not learn online on live prices. "Continuous" means scheduled walk-forward
  retraining on closed years, promoted through the engine swap.
- It must not report a mean over seeds or over years without the spread beside it.
- It must not hide the maximum-profit configuration behind the optimal one, or the reverse.
- It must not add a lever, a feature or a data source without saying which measured
  blindness it fixes.
