# System 10 — the conditioned policy

*Opened 2026-09-27. The plan is `.meshkore/context/system10-design.md`; the initiative is
`.meshkore/roadmap/initiatives/system-ten-conditioned-rl.md`; the tasks are S10-1..S10-12.*

## 1. Hypothesis

The best trades in this market do not happen everywhere. They cluster under a small set of
causal conditions, and a learner spread evenly over every candle of every year spends most
of its capacity on bars where there was nothing to win.

So: locate that region from the teacher's own best trades, and train a policy **inside it
only** — a policy that sees the book as well as the market, and is rewarded by the
operator's criterion (profit against drawdown, after costs) rather than by a proxy for it.

The claim is not "reinforcement learning is better than supervised learning". It is that
**what system 06 cannot express is the trade-off between a position and the slot it
occupies**, and that a policy rewarded on portfolio outcomes inside a region where the edge
is dense can express it. The gap being aimed at is measured, not assumed: on the same
297,730 entries, the hindsight exit returns +30.86% a trade and the shipped rule +0.44%
(`research/system06/tools/exits.py`).

## 2. What it is

Nothing is trained yet. What exists is the package skeleton, registered and **abstaining**,
and the plan the twelve tasks execute. The design:

- **State** — system 06's 44 causal features over a 96-bar window of 15-minute candles on 14
  pooled USDT pairs, plus **book state**: position flag, unrealised return, bars held, slots
  free, distance from the year's equity peak, and the region's regime id.
- **Actions** — `{abstain, enter half-slot, enter full-slot, hold, exit}`. Long-only, spot,
  three slots.
- **Reward** — per bar, Δ log equity − λ·Δ drawdown-from-peak − the costs the backtester
  charges; terminal, the Q criterion `sign(r)·r²/max(dd, 0.02)`.
- **Region R** — an interpretable causal predicate fitted on years ≤ N−1 covering ≥80% of the
  oracle's top-quantile swings. System 06's gates are version zero of R and are scored
  first. Coverage per year is a deliverable, and the feasibility bootstrap is run *inside* R.
- **Environment** — the frozen backtester's ledger, called and never re-implemented, with a
  golden test that replays 06's champion decisions and matches `launch.per_year` to the cent.
- **Training order** — behaviour cloning of 06 (the baseline), then offline RL (CQL/IQL),
  then PPO, then an action-vote ensemble; each step gated on two validation years.
- **Data** — 15m candles for 14 symbols from the shared catalogue, research to 2025-12-31;
  2026 sealed and read once.

**The region as found (S10-6, fitted on 2017-2024, 80% of the top-20% swings):**
`pct_below_high_55 <= -2.4%` with `bb_width > 3.6%` and either `natr_14 > 2.0%` or
`aroon_down > 70`; or `pct_below_high_55 > -2.4%` with `return_5 > 1.3%` and
`aroon_osc <= 34`. In words: the best swings start in volatile pull-backs and in fresh
bursts. 14% of the tape. Out of sample it did not beat entering anywhere (RESULTS.md).

## 3. What helped

Not yet written up — nothing has been measured. The first rows will come from S10-6 (the
region's coverage) and S10-8 (the cloning baseline and what, if anything, beats it).

## 4. What hurt

Not yet written up. Three things are already known to be *unavailable* to this system,
inherited from the record rather than measured here, and they constrain the design:

| Inherited refusal | Where it was measured | What 010 does about it |
|---|---|---|
| Averaging the probabilities of identically-trained nets loses (bag of 3: −0.1587) | 06's A43, A48, P22 | any 010 ensemble votes over **actions**, never averages scores |
| Turnover levers fitted on the full record describe a dead market | 06 rule 6; A128, closed 2026-09-18 | validation years are the modern ones; 2021 is down-weighted and never carries a verdict |
| A per-entry edge is not a portfolio edge (hold 384 wins per entry, scores −0.5252 in the book) | 06's P59 | the reward is portfolio equity, and the policy sees the slots |

## 5. What is still open

Everything. In the order the tasks answer it:

- Does a region covering 80% of the best trades leave enough of the tape for a three-slot
  book to deploy in? (S10-6 — and a named kill condition if it does not.)
- Does `P(year ≥ +20%)` inside the region clear 50% on the *capturable* return? (S10-6.)
- Can anything beat behaviour cloning of 06 on two validation years? (S10-8. If not, the
  honest finding is that 06's decision rule is the best policy we could find.)
- Is the seed spread narrower than the edge? (S10-8; the laboratory's own P54 puts the seed
  alone at up to 0.21 of the consistency score.)

## 6. Rules learned

Not yet written up. The rules this system was *built on* are in
`.meshkore/context/LESSONS.md` — 40 of them from eight systems — and the two that shaped
this design most are: training return does not rank forward return (system 04, +495% in
training and −5.81% sealed), and price the odds before spending a sealed reading.
