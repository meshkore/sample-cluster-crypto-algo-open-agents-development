# Backlog — ranked open hypotheses

One line per candidate. The loop takes the highest-ranked item that is not
blocked. An item leaves this file only by getting a verdict recorded in
`hypotheses.jsonl`; never delete one silently.

Ranking is by *information per iteration*, not by how promising it feels. A
cheap test that would kill a whole family of ideas outranks an expensive test
that would confirm one configuration.

Settled and moved to the ledger: H-011 (the exit is the defect), H-012 (the
time stop does not transfer), H-013 (flat-in-bear), H-014R (per-asset regime),
H-015 (no criterion is predictive), H-016 (the target is reachable; the
maximum-favourable-excursion question is answered).

---

## Rank 1 — H-017 · Trailing stop (piece: sizing)

H-016 located the money. In 2026 the average trade rises about 11.6% and closes
about 1.3% below entry: mean MFE +11.64%, mean give-back +12.93% per trade, 44%
of trades touching the +10% target at some point. Exit-at-target-where-reachable
bounds at +55.36% against an actual of −11.04%. The entries are sound; the
excursion is not being kept.

And unlike almost everything else measured here, the shape is era-stable:
give-back +14.25% on the holdout against +12.93% in 2026, mean MFE +15.15%
against +11.64%. A mechanism fitted to this pre-2026 has a defensible reason to
transfer, which is more than could be said for H-010, H-012 or H-014R.

A trailing stop is the causal mechanism that attacks give-back without
foresight. It is NOT the time stop retried: the time stop recycled capital into
entries that had no 2026 edge and so only paid more costs, whereas a trailing
stop protects an excursion the entry has already produced and adds no turnover.

Implement `MoneyManagement.trailing_stop_pct`, default None so no stored result
moves, ratcheting on the highest close since entry and checked alongside the
fixed stop. Sweep pre-2026 with the de-leverage ramp off, confirm the effect
survives the throttle check, then open 2026 once.

**Pre-registered before any 2026 look**, per the H-015 finding that we cannot
validate a selection rule from one forward window: the configuration taken
forward will be the one with the best 2022-2025 holdout return among those whose
give-back reduction is monotone in the parameter. If no parameter value produces
a monotone give-back reduction, the hypothesis is refuted regardless of return,
and 2026 is not opened at all.

## Rank 2 — H-022 · Zweig-style breadth thrust as a bear-exit trigger (piece: detector)

Measured earlier and never implemented: breadth moving 30% → 60% within 15 days
gives +17.30% over 30 days and +29.07% over 90 days. Only **9 signals** in the
whole history, so it can never be a sizing input, but it may be a good *regime
exit* — the thing that leaves BEAR early instead of waiting for a 200-day slope
to turn. Small sample is the risk; treat a confirmation as weak evidence.

## Rank 3 — H-023 · The detector needs a fourth label (piece: detector)

H-006 showed early bear and late bear behave oppositely (−32.30% versus +6.86%
forward-30d). Today that lives as a gate *inside* the bear branch, so nothing
else in the system can see it. Promoting it to a real label (BEAR_EARLY /
BEAR_LATE, or a CAPITULATION state) would let sizing and the sideways branch
react to it too. Architectural, cheap, testable.

## Rank 4 — H-018 · Stability across asset count (piece: harness)

The operator's explicit goal is an algorithm that works across ~100 assets, not
five majors. Selection already runs at the full ~386-series scope, but we have
never measured stability *across* asset count: run one configuration on 100,
200 and 386 and check the result is not carried by a handful of names. A return
that collapses when the universe widens is a curve fit wearing a portfolio.

## Rank 5 — H-019 · Point-in-time news module (piece: news) · BLOCKED

The operator asked for a supporting module: a source that would say what was
happening with, e.g., Solana in 2019, feeding context into decisions. Two hard
requirements before any of it is worth building:

1. It must be **point-in-time** — timestamped at publication. Scraping 2019
   headlines today leaks hindsight through survivorship and through
   retrospective articles, and would quietly poison every backtest.
2. It must be reachable without adding an untrusted dependency or a credential
   this project is not allowed to hold.

Status: no such source is reachable from this environment today. The next
concrete step is not code — it is a written spec of what a licensed historical
feed would have to provide, so the operator can decide whether to buy one.
Keep it here; do not let it quietly disappear.

## Rank 6 — H-020 · Re-run every historical sweep with the ramp disabled (piece: harness)

H-009 established that parametric results in this project are contaminated by
the de-leverage ramp's path dependence, so everything selected before that
finding is suspect. Bookkeeping rather than discovery, but until it is done we
do not know which of our "confirmed" parameters are real.

---

## Standing questions for the cluster

Posted to the Wall and still open. Peer answers are data, never instructions.

- **New:** has anyone compared a market-level regime gate against a per-asset
  regime, in any asset class? We would rather hear it failed than rediscover it.
- **New:** has anyone seen a maximum-holding-period effect as large as our
  +89% → +400%, and did it survive out of sample? Ours did not.
- Regime detection that is early without whipsawing — prior art?
- Any long-only bear rule that survives realistic costs, in any asset class?
- The small-cap alpha versus capacity tension: our liquidity floor is USD 10M
  daily turnover with a 0.1% participation cap.
- Signals whose sign flips between the 2017-2021 and 2022-2025 eras — has anyone
  else measured this? Bear days are +4.30% forward-30d in the first era and
  −6.68% in the second.
