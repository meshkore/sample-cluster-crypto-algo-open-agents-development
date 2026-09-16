# System 09 — postmortem

*Written 2026-09-16, when the world model was split out of this repository and the trading
laboratory went back to being only a trading laboratory. System 09's development was stopped
by the operator on 2026-09-15. This page exists so the work is not lost and so nobody has to
re-derive what it already established.*

**Status: v1 complete, stopped, preserved and runnable.** Not abandoned and not deleted.

---

## What it was

The hypothesis, in one sentence: **the forecastable part of crypto returns is driven by who is
constrained, not by chart shape** — who has run out of cash, who is underwater and by how much,
who is levered near a liquidation band, who is mechanically obliged to rebalance.

So the system reconstructed **every participant's balance sheet**, from the first day Binance
has a tape to the end of 2025, as a closed sector with a short boundary: a double-entry,
stock-flow-consistent ledger in which every trade is a conserved transfer between behavioural
cohorts and the totals move only through five named boundary channels. Then it trained a model
on how those players actually behaved, and asked it to say what they would do next.

That is the idea the operator described as *"simulating the portfolios of all the players"*,
and it is worth being clear that **the idea is not what failed**.

## What was built

| | | |
|---|---|---|
| Phase 1 | the whole record reconstructed — every asset from the day it first trades, players born and retired against observed activity, balances struck at 2025-12-31 | `python -m system009_participant_ledger.phase1` |
| Phase 2 | a model trained on how those players behaved | `python -m system009_participant_ledger.train` |
| Phase 3 | the sealed 2026 forward test | `python -m system009_participant_ledger.phase3` |
| Phase 4 | the local dashboard: totals, market cap, balances by segment, the 2026 section | `research/system09/preview/server.py`, port 8709 |

**Scale of the reconstruction:** 177,699 dollar-volume buckets, 3,059 days, 14 assets, 105
players at the open and 435 at the 2024 peak, **no fitted parameters at all** — every
behavioural constant is an unfitted prior.

**The accounting held.** Unit drift of −1.03e-14 relative and $0.058 of cash drift on a $560bn
pool, over eight years and 177,699 settlements, with the invariant asserted at every daily
close. That is float64 rounding, and it is the part of this system that is unambiguously good.

## What it measured

The sealed 2026 window was opened **four times**, each time after a structural defect had been
found and fixed — and none of the four defects was found by looking at the 2026 P&L.

| | R1 | R2 | R3 | R4 |
|---|---|---|---|---|
| Return | −16.07% | −0.52% | **+17.85%** | −4.45% |
| Model IC on the sealed rows | +0.1325 | +0.1927 | **−0.0553** | +0.0028 |
| Success ratio | 46.5% | 49.3% | 47.2% | 46.5% |
| Buy & hold universe | −7.7% | −7.8% | −7.8% | −7.7% |

**The +17.85% is the one to be most suspicious of, and the laboratory was, at the time.** It
came with a *negative* skill statistic on the same rows: the model ranked assets worse than
chance and the account still went up. That is profit without skill, and it was not quoted as a
result then and must not be quoted as one now.

**The finding is the spread, not any single number.** Four structural corrections the market
never sees moved the same year's return across 34 points. Meanwhile the one statistic that
stayed honest — rank correlation on the sealed rows — went +0.13, +0.19, −0.06, +0.00, against
+0.14 in the research folds. **It averages to nothing. The ledger features, as built, do not
generalise.**

## What was NOT established

That the approach is wrong.

The v4 reconstruction matches the published float of every asset to 0.00% — a better instrument
than any of the four readings were taken with, and it has never been trained on properly.
Purged folds, ensembles and the macro layer were all still ahead when the work stopped. **The
verdict is about v1's evidence, not about the idea.**

## Why it stopped

Not because of the results. On 2026-09-15 the operator stopped trading-system development
outright and redirected the effort into a simulation of the world economy, which became its own
project the following day. System 09 was mid-flight and is left where it stood.

## The state it is left in

- **Every module imports and runs** — verified 2026-09-16, 26 of 26.
- **The World Archive is gone from this repository.** It left with the world model. The world
  and regional blocks now **degrade to zeros and say so once on stderr**, which is this
  laboratory's own stated position — *missing is ZERO, and that is a statement* — and is safe
  here because the ablation of 2026-09-15 established those blocks **do not belong in the
  cross-sectional model**: the held-back year fell from +0.111 to −0.066 when they were added.
- **One exception, which refuses instead of degrading:** `market_model.py`, the market-direction
  head, whose entire question is what the world outside crypto says. It raises rather than run
  on zeros, because that would be a different experiment reported under the same name.
- **To restore the world data**, put the world model's root on `PYTHONPATH` so that `mwmodel`
  imports; `world.ARCHIVE` then reports `True` and the blocks populate. Verified working
  across the two repositories on 2026-09-16.
- **The autoloop's `exp_archive` guard was removed** — a health check for a package that is not
  here fails for the one reason that tells you nothing.
- `research/system09/STOP` halts the loop; it is stopped.

## If this is ever resumed, the three things that are already known

1. **The sealed window is spent.** Four readings deep. v2 needs a period this system has never
   touched, sealed before a line of it is written. Re-reading 2026 proves nothing about 2026.
2. **Price the odds before building.** A P&L whose year-to-year spread straddles zero has not
   earned a sealed reading — this laboratory has lost that bet three times out of three.
3. **Accuracy about the world and profit are not the same axis.** The most calibrated
   reconstruction of the four is not the most profitable one, and that is not a paradox to be
   explained away.

*Full evidence: [`RESULTS.md`](RESULTS.md) — all four readings, the accounting checks, the
fidelity-to-tape tables and the ablations. Design: `.meshkore/context/system09-design.md`.*
