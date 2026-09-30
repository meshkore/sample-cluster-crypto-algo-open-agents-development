# System 10 - design dossier (S10-3)

*Written 2026-09-30. Argues every default of `.meshkore/context/system10-design.md` section 4
against the published record. No scripts were run and no numbers of our own appear here;
every number quoted is the cited paper's. Sources are keyed [S#] and listed at the end, and
each has a line in `knowledge/sources.jsonl`. Anything marked **(our reasoning)** is an
inference, not a citation.*

**One-paragraph verdict.** The design survives the record in shape: book state in the state,
a small discrete action space, the backtester's full cost model, clone first, offline RL
second, voting over actions. Four things change. (1) The **terminal Q reward** goes, because
TD learners collapse when the return arrives only at the end [S4]. Q becomes the
*selection* criterion instead. (2) The offline dataset must be **mixed** (oracle + clone +
perturbed), not "clone plus perturbations", because conservative Q-learning gains most on
mixed data and least on narrow data [S2]. (3) **PPO is replaced** by online fine-tuning of
the offline learner, early-stopped on validation. The only published method here designed
for offline-then-online is IQL [S3], and PPO in trading environments shows in-sample up while
out-of-sample goes down [S11]. (4) Validation adds a **trial ledger and a probability of
backtest overfitting** across all arms, because walk-forward on one history is the easiest
scheme to overfit [S15, S17, S9]. The λ of the drawdown penalty has **no published
cost-surviving evidence** at any value, so it is swept against a λ = 0 control and every λ
counts as a trial.

---

## 1. State

**Default.** 06 feature window (44 x 96) + book state (position flag, unrealised return,
bars held, slots free, distance from the year's equity peak) + regime cluster id.

| Supports | Contradicts |
|---|---|
| Moody & Saffell: optimal decisions under transaction costs "require knowledge of the current system state"; the trader feeds back its previous position [S5]. | Nothing found against book state. |
| Jiang et al. put the previous portfolio weights into the input "for the RL agent to consider the effect of transaction cost" (the Portfolio-Vector Memory) [S7]. | |
| The FinRL contests' benchmark state carries holdings `h_t` beside the market features [S8]. | |
| Decision Transformer did significantly worse with context K = 1 than with K = 30-50 [S4]. This is weak support for a long window. | |

**What the design does.** Confirms the default. Two notes:
- The distance from the equity peak must stay in the state if the reward penalises
  drawdown. Otherwise the reward depends on something the policy cannot see **(our
  reasoning)**.
- The regime id comes from a region learner fitted on years <= N-1. It inherits that
  learner's purge (see Validation).

## 2. Actions

**Default.** Discrete `{abstain, enter half, enter full, hold, exit}`, long-only spot.

| Supports | Contradicts |
|---|---|
| Zhang, Zohren & Roberts use a discrete `{-1, 0, 1}` for DQN and PG. DQN "obtains the best performance among all models"; A2C (continuous) generates larger turnover [S6]. | 2501.10709: in a restricted action space, ensemble members "may be converging", giving "near-identical" results between ensembles and individuals [S1]. So a small action space weakens a vote *unless the members are made diverse* (see Q3). |
| In a Forex RL framework, the simplified 3-action adapter gave "higher Sharpe and lower drawdown" than a 10-action interface. That was on the training period only [S12]. | |
| The same framework applies **legal-action masking** during both training and replay [S12]. | |

**What the design does.** Confirms the default and **adds legal-action masking**: enter
only when a slot is free and R(t) = 1; hold and exit only when in a position; abstain only
when flat [S12]. This removes impossible actions from the Q-targets and from the vote.

## 3. Reward

**Default.** Per bar: Δ log equity - λ·Δ drawdown-from-peak - backtester costs. Terminal:
Q = sign(r)·r² / max(dd, 0.02).

What the record shows (full answer in Q2 below):

| Evidence | Reward | Out of sample, net of costs? |
|---|---|---|
| Moody & Saffell 1998 [S5] | differential Sharpe (DSR), recurrent RL | **Yes.** 25-year ex-ante walk-forward on S&P 500 / T-bill, 0.5% cost, profits reinvested; the committee vote has Sharpe 0.83 against buy-and-hold 0.34. |
| Zhang et al. 2020 [S6] | additive profit, volatility-scaled, with the cost term in the reward | **Yes.** 50 futures, 2011-2019, retrained every 5 years; DQN and A2C "still generate positive profits with cost rate at 25bp". |
| Hanetho 2023 [S13] | net log return - λ·variance (60-bar) | **Yes, one market.** Natural gas, λ ∈ {0, 0.01, 0.1, 0.2}. λ = 0.01 gave the best Sharpe; λ = 0.1 and 0.2 cut returns by 25% and 38%. |
| Nawathe et al. 2024 [S14] | DSR vs profit | Single test window (2018-2019). DSR is "a difficult reward"; profit won; DSR was "difficult ... to overfit". |
| Abbade & Costa 2026 [S11] | DSR - λ_dd·(ΔDD⁺)² | λ tuned by Optuna **on out-of-sample Sharpe**, which is selection on the test set. No λ value or isolated ablation in the text read. |
| Saidd 2026 [S12] | 11 components incl. drawdown weight 0.05 | **Training period only**; effects "non-monotone". |
| Chen et al. 2021 [S4] | delayed (terminal-only) return | CQL "fails" when rewards are delayed to the last step. DT and %BC are barely affected. |

**What the design does.**
- **Keep** the per-bar Δ log equity net of the backtester's costs, including √participation
  impact. The cost model changes which algorithm ranks first [S11], and 06's costs are the
  ones the book pays.
- **Keep** λ·Δ drawdown as the lever for the operator's "monetary safety is a priority",
  but treat it as an *objective choice*, not a neutral shaping term. Finance penalties such
  as drawdown "are generally not policy-invariant" [S12, citing Ng et al. 1999, which could
  not be read]. There is no published λ to copy. λ is swept on a pre-declared grid that
  includes **λ = 0 as the control (the maximum-profit configuration)**, and each λ is a
  trial in the ledger (Validation).
- **Remove the terminal Q from the reward.** Use Q to *rank* on validation years, where it
  already lives in `tools/quality.py`. The reasons: a TD learner (CQL) collapses on
  end-of-episode returns [S4]; Q is a ratio over the whole year, not a sum of per-bar terms
  **(our reasoning)**; and the published way to put a ratio objective into a per-bar reward
  is the differential form [S5].
- **Add a DSR arm** as the second reward family to test. It is the only risk-adjusted per-bar
  reward with a long cost-surviving out-of-sample record [S5]. [S14] warns that it learns
  more slowly.

## 4. Episodes

**Default.** One calendar year, fresh $100,000; 2021 down-weighted.

| Supports | Contradicts |
|---|---|
| Moody & Saffell retrain once a year on a moving 20-year window and trade the next year ex ante [S5]. That is the same year-by-year unit. | Gort et al.: walk-forward "validates in one market situation", and the validation period "can be biased, e.g., a significant market uptrend" [S9]. This supports down-weighting a dominant year; nothing argues against it. |
| Zhang et al. freeze parameters for 5 years between retrains [S6]. Coarse retraining is standard. | |

**What the design does.** Confirms the default. Episodes matter only for the per-bar reward's
drawdown reset and for any return-to-go. The offline learner consumes transitions.

## 5. Algorithm order

**Default.** (1) Behaviour cloning = 06 → (2) offline RL (CQL or IQL) on transitions replayed
under the clone plus perturbations → (3) PPO if (2) beats (1) on two validation years → (4)
action-vote ensemble if seed spread > edge.

| Step | Supports | Contradicts / refines |
|---|---|---|
| 1 BC baseline | BC is the standard baseline in CQL [S2], DT [S4] and Kumar et al. [S10]. Several works "argued that BC performs better than offline RL" [S10]. | 06 already clones a **hindsight-best** labeller. That is close to DT's "%BC" (cloning only the top X% of trajectories), which "can match or beat other offline RL methods" when data is plentiful [S4]. **The bar for step 2 is high.** Report that honestly. |
| 2 offline RL | CQL learns a lower-bound Q against "overestimation of values induced by the distributional shift" [S2]. It has a discrete-action variant evaluated on Atari [S2]. IQL "never" queries unseen actions [S3]. Offline RL beats BC with noisy, suboptimal data on long horizons [S10]. The clone is suboptimal. | CQL's gains are largest on **mixed** datasets ("medium-expert", "random-expert"); on single-policy data it wins "by a small margin" [S2]. A narrow expert dataset produced an "unlearning" effect in policy-constraint methods [S2]. IQL was evaluated on continuous control only. With stochastic dynamics its upper expectile can chase a "lucky" transition [S3]. Markets are the extreme case **(our reasoning)**. |
| 3 PPO | None found for PPO after offline RL in trading. | PPO in the margin-trading environment: "IS return rises slightly while OOS declines over epochs"; A2C peaks near epoch 15 and degrades [S11]. IQL is the method the record shows for this step: it "achieves strong performance fine-tuning using online interaction after offline initialization" [S3]. |
| 4 vote | See Q3. | See Q3. |

**What the design does.**
- Step 2: CQL (discrete) first, then IQL with a moderate expectile, both on a **mixed
  dataset**: oracle actions + clone actions + ε-perturbed clone + random actions, all
  replayed through the backtester [S2]. The oracle's *actions* are legal behaviour data
  because states remain causal **(our reasoning)**.
- Step 3: **online fine-tuning of the step-2 learner** (IQL's own procedure [S3]), not PPO
  from the clone. Evaluate on validation after every epoch and stop early. Moody & Saffell
  early-stop on a validation window [S5], and [S11] tracks out-of-sample performance epoch
  by epoch. "Online" here is always the backtester over closed years, never live prices.
- Decision Transformer is **not adopted**. It helps most with sparse or delayed rewards and
  low data [S4]. We keep a dense reward, and 06 already fills the %BC role.

## 6. Region

**Default.** An interpretable causal predicate fitted on years <= N-1, covering >= 80% of
the oracle's top-quantile swings. 06's gates are version zero.

| Supports | Contradicts |
|---|---|
| Kumar et al.: offline RL beats BC most clearly when there are few "critical" states where the expert's action matters [S10]. The region is a claim that those states are concentrated. | DT: "the only way to choose the optimal subset for cloning is to evaluate using rollouts", so the %BC cut is "not a realistic approach" as a free parameter [S4]. **The region width is a hyperparameter**, and choosing it costs trials. |
| CQL: Q training does not suffer from state shift, "however, the policy may suffer from state distribution shift at test time" [S2]. Consulting the policy only inside R narrows the test-time state distribution to where it was trained **(our reasoning, built on [S2])**. | |

**What the design does.** Confirms the default. The region width chosen by S10-6's
arithmetic is logged as a trial, and its validation reading counts against the trial budget.

## 7. Validation

**Default.** Purged walk-forward by year, 96-bar embargo, four seeds, spread and worst year
reported, selection on validation years only.

| Supports | Contradicts / refines |
|---|---|
| Purging: labels that share information with the test set must be removed, or an embargo applied [S17]. Walk-forward by year matches how the system would be retrained [S5, S6]. | Walk-forward is "very easy to overfit because only 1 history is tested" [S17]. "Using a single validation set can easily result in model overfitting" [S9]. |
| "Every backtest must be reported with all trials involved in its production" (deflated Sharpe) [S17]. | With five years of daily data and 45 or more independent variations, the best one is "more than likely" to show Sharpe >= 1.0 by chance [S15]. |
| | Seeds: two groups of 5 seeds with the *same* hyperparameters produced "statistically different distributions". Averaging N < 5 trials "can be potentially misleading" [S16]. |
| | Gort et al. reject DRL crypto agents whose estimated probability of backtest overfitting is above 10% [S9]. |

**What the design does.**
- Keep walk-forward by year as the primary reading.
- **Add a trial ledger.** Every arm (algorithm step, λ, reward family, region width,
  expectile, ensemble size) is recorded, and the count is reported beside every result [S17].
- **Add PBO (combinatorially symmetric CV) over the ledger** on research years. Reject a
  winner whose PBO exceeds 10% [S9].
- **Raise seeds from 4 to 5** for the gated comparisons (clone vs offline RL, offline vs
  fine-tuned) [S16]. Spread is still reported, never a mean alone.
- **Embargo:** at least 96 bars, and at least the longest oracle-swing span used to fit R
  where it crosses a fold boundary. That is the purge definition [S17] applied to the
  region's labels **(our reasoning)**.

## 8. Compute

**Default.** RTX 4060 8 GB. One heavy training at a time; 010 brakes 06's genome search
while it trains; the environment replay runs on CPU in parallel.

| Supports | Contradicts |
|---|---|
| Offline RL separates data collection from learning [S2, S3]. Transitions are generated once on the CPU through the frozen backtester, then trained from a buffer on the GPU. That fits a single 8 GB card. | The FinRL line gets up to 1,746x sampling speed from 2,048 GPU-vectorised environments [S1]. That needs a re-implemented ledger, which the laboratory forbids. On-policy steps are therefore **CPU-bound** here. That is a cost to price before step 3, and one more reason step 3 is IQL fine-tuning rather than sample-hungry PPO **(our reasoning)**. |

**What the design does.** Confirms the default. No vectorised re-implementation of the
ledger.

---

## Q1. Offline before on-policy

- **What offline RL fixes.** It fixes *action* distribution shift: overestimated values for
  actions the data never took [S2, S3]. Q training "does not suffer from state distribution
  shift", but the policy can at test time [S2]. One price history means the *states* (the
  market) are fixed. The book state and the actions can still be explored in the
  backtester. So the offline step protects against value overestimation. It does **not**
  protect against a new year looking unlike the old ones. Only walk-forward and PBO read
  that (section 7).
- **When it beats cloning.** Offline RL beats BC with noisy, suboptimal data on long
  horizons, or when few states are critical [S10]. When data is plentiful, cloning the best
  subset matches offline RL [S4]. 06 is roughly that clone, so step 2 must clear a strong bar.
- **What the FinRL record says fails out of sample.**
  - In the 2023 contest's second test week, teams had negative returns; the organisers
    write that "generalization to new, unseen market conditions remains a challenge" [S8].
  - The crypto winners were tested over about two days of second-level data: +0.23%
    (2024) and -0.05% (2025) [S8].
  - The ensemble paper's crypto out-of-sample window is 45 minutes [S1].
  - Jiang et al. tested on roughly 50-day windows and name "zero market impact and zero
    slippage" as their main weakness [S7].
  - Gort et al.: existing crypto DRL work "optimistically reported increased profits in
    backtesting", which may be false positives [S9].
  - The on-policy learners in [S11] diverge in-sample vs out-of-sample over epochs.

  None of these publishes a multi-year, cost-inclusive out-of-sample record comparable to
  our exams. **So the design stays offline-first**, and "beats the clone on two validation
  years" is the only gate that matters.

## Q2. Reward shaping with drawdown

- **Differential Sharpe.** This is the only risk-adjusted per-bar reward with a long
  out-of-sample, cost-inclusive record: 25 years ex ante at 0.5% cost [S5]. [S14] finds it
  harder to learn than profit.
- **Per-bar drawdown penalty.** No source read gives cost-surviving out-of-sample evidence
  for any λ. [S11] tuned it on the out-of-sample set and reports no value in the text read.
  [S12] uses a weight of 0.05, on the training set only.
- **The nearest published λ sweep is a *variance* penalty.** λ ∈ {0, 0.01, 0.1, 0.2} on
  60-bar log-return variance, out of sample and net of costs, one market. λ = 0.01 gave the
  best Sharpe, and larger λ cut returns by 25-38% [S13]. That is evidence about the *shape*
  (small λ helps, large λ trades return away), not a value to copy into a drawdown term.
- **Terminal Q.** No evidence. TD learning "collapses" on terminal-only returns [S4].
- **Rule 010 adopts.**
  - Per-bar Δ log equity net of full backtester costs, minus λ·max(0, Δ drawdown).
  - λ is swept on a small grid declared before training, with λ = 0 as the control. Both
    the maximum-profit arm (λ = 0) and the Q-optimal arm are reported, as the laboratory
    requires.
  - A DSR arm is added as the cited alternative.
  - Q is used only to rank arms on validation years.

## Q3. Ensembles over actions, not probabilities

- **What 2501.10709 actually did** [S1]. It uses *both* rules.
  - The **stock** task uses "weighted averaging over the agents' action probabilities"
    (Sharpe-softmax weights). The top ensemble did **not** beat the best single agent on
    return: 62.60% vs PPO's 63.37%.
  - The **crypto** task uses "majority voting to combine the actions". There the ensembles
    beat every individual, but over a 45-minute test, and the authors report "near
    identical" behaviour caused by "a lack of diversity".
  - Diversity was forced with a KL-divergence term between members.
  - The knowledge-base line for this paper (system 06) should be read with that correction:
    only its crypto half votes over actions.
- **Stronger precedent.** Moody & Saffell trade "a majority vote of the ensembles" of 30
  RRL traders, over 25 years at 0.5% cost [S5].
- **Rule 010 adopts.**
  - An odd number k >= 3 (5 when compute allows) of independently trained policies.
  - Each member returns one legal, masked action; no scores leave a member.
  - When flat, the actions are ordered by resulting exposure (abstain = 0 < half < full),
    and the ensemble takes the **median vote**. That is the largest exposure a majority
    supports; with k odd it is always defined.
  - When in a position, the rule is a **strict majority to hold; a tie or a minority exits**.
  - The conservative tie-break is the laboratory's safety preference **(our choice,
    uncited)**.
  - Members must differ by more than seed: different walk-forward fold windows or bootstrap
    samples, following Moody's bootstrap-trained Q-trader [S5], and optionally a KL
    diversity term [S1]. Seed-only members risk the "near-identical" failure [S1] and A43's
    identically-trained-net failure.
  - The ensemble is still tried only if the seed spread exceeds the edge. A48 already showed
    that shrinking spread pulls toward the mean, not the good tail.

---

## Changes proposed to section 4

1. **Reward:** drop the terminal Q from the reward and use Q only to rank arms on validation
   years. Keep per-bar Δ log equity - λ·Δ drawdown net of full costs. Sweep λ on a
   pre-declared grid with λ = 0 as the control. Add a differential-Sharpe arm [S4, S5, S12,
   S13].
2. **Actions:** add legal-action masking in training, replay and voting [S12].
3. **Algorithm step 2:** CQL (discrete) first, then IQL, on a **mixed** dataset (oracle +
   clone + perturbed + random actions), not "clone plus perturbations" [S2, S3].
4. **Algorithm step 3:** replace PPO with online fine-tuning of the offline learner (IQL
   procedure), early-stopped on validation each epoch [S3, S5, S11].
5. **Ensemble:** odd k, legal actions only, median-exposure vote when flat, strict majority
   to hold. Members diversified by fold or bootstrap, not seed alone [S1, S5].
6. **Validation:** add a declared trial ledger and PBO across all arms with 10% rejection.
   Raise seeds from 4 to 5 for the gated comparisons. Embargo = max(96 bars, longest
   oracle-swing span used by R) [S9, S15, S16, S17].
7. **Region:** its width is a logged trial [S4].
8. State, episodes and compute: **confirmed unchanged.**

## Sources

| Key | Source | Read? |
|---|---|---|
| S1 | Holzer, Wang, Xiao, Liu - Revisiting ensemble methods for stock and crypto trading, arXiv 2501.10709 | full text |
| S2 | Kumar, Zhou, Tucker, Levine - Conservative Q-Learning, arXiv 2006.04779 (NeurIPS 2020) | full text |
| S3 | Kostrikov, Nair, Levine - Implicit Q-Learning, arXiv 2110.06169 | full text |
| S4 | Chen et al. - Decision Transformer, arXiv 2106.01345 (NeurIPS 2021) | full text |
| S5 | Moody & Saffell - Reinforcement learning for trading, NIPS 1998 | full text |
| S6 | Zhang, Zohren, Roberts - Deep reinforcement learning for trading, arXiv 1911.10107 (JFDS 2020) | full text |
| S7 | Jiang, Xu, Liang - A DRL framework for the financial portfolio management problem, arXiv 1706.10059 | full text |
| S8 | Wang et al. - FinRL Contests: benchmarking data-driven financial RL agents, arXiv 2504.02281 | full text |
| S9 | Gort, Liu et al. - DRL for cryptocurrency trading: addressing backtest overfitting, arXiv 2209.05559 | full text |
| S10 | Kumar, Hong, Singh, Levine - When should we prefer offline RL over behavioral cloning?, arXiv 2204.05618 (ICLR 2022) | intro + theory |
| S11 | Abbade & Costa - Realistic market impact modeling for RL trading environments, arXiv 2603.29086 | full text |
| S12 | Saidd - Decomposable reward modeling for RL Forex trading, arXiv 2604.00031 | full text |
| S13 | Hanetho - Deep policy gradient methods in commodity markets, arXiv 2308.01910 (thesis) | method + results |
| S14 | Nawathe et al. - Multimodal DRL for portfolio optimization, arXiv 2412.17293 | full text |
| S15 | Bailey, Ger, López de Prado, Sim, Wu - Statistical overfitting and backtest performance (LBNL) | full text; reports the Bailey et al. 2014 result |
| S16 | Henderson et al. - Deep reinforcement learning that matters, arXiv 1709.06560 | full text |
| S17 | Notes on López de Prado, *Advances in Financial ML* (reasonabledeviations.com) | secondary notes, not the book |
| S18 | Borrageiro, Firoozye, Barucca - The recurrent RL crypto agent, arXiv 2201.04699 | abstract + setup |

S18 is context for Q2: a direct-RL crypto agent that is net positive after 5 bps fees, but
71% of its return is funding profit, so it is not evidence of a trading edge.

**Could not be reached. Nothing above is taken from these.**
- Moody & Saffell, *Learning to trade via direct reinforcement*, IEEE TNN 2001: the PDF
  mirror returned 403 and the publisher version is closed. S5, the same authors' NIPS 1998
  paper, is cited instead.
- Deng et al., IEEE TNNLS 2017: paywalled.
- MDPI 2026 *Innovative reward functions in RL for crypto trading*: 403.
- Bailey, Borwein, López de Prado & Zhu, AMS Notices 2014: bot-blocked. Its 45-trial result
  is cited through S15, written by overlapping authors.
- The López de Prado book itself: S17 notes are used.
- Ng, Harada & Russell 1999: the PDF text was unextractable. The shaping claim is cited
  through S12.

Status: awaiting operator agreement
