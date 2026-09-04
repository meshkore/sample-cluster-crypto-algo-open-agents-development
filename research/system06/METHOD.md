# How this system is improved

Written 2026-09-04, after the operator asked the fair question: *are we iterating at
random, or are we correcting step by step?*

`rnd/LOOP.md` is the harness — the tick protocol the agent walks. This file is the
narrower thing the harness cannot supply: the **method for turning a weakness into a
fix**, and the list of places where that method is enforced by code rather than by
memory. Prose that only lives in a document has been forgotten in this project four
times; every rule below therefore names the file that makes it non-optional, or admits
that it does not have one yet.

---

## The rule that generated the rest

**Diagnose before you prescribe.** An experiment is only worth GPU time if a
measurement already says which quantity it should move.

This is not a general principle, it is a bill for work already paid. P42 walked the
entry bar down. P44 spread across more names. P46 walked the bar up and paid for the
lost breadth with size. Three experiments, three refutations, and none of them was
aimed at anything measured — all three were plausible cures proposed before anyone had
located the disease. The measurement that would have redirected all three took four
minutes to run once it was written.

So: **no experiment enters the queue without naming the measurement that motivated it.**

---

## The five steps

### 1. Find where the system actually fails, in arithmetic
Not "it underperforms" — *which year, which regime, which decision*. The mandate is
+30% every calendar year, so any year below that is a failure with a name and a date.

Current standing answer: 2022 (+8.7%) and 2025 (−2.96%).

### 2. Establish what KIND of failure it is before proposing anything
The three kinds are distinguishable and they take opposite cures:

| kind | signature | cure lives in |
|---|---|---|
| the trades are wrong | low hit rate, negative average trade | the model, the features, the labels |
| the trades are too few | high hit rate, few trades | the gates, the regime filters |
| the trades are too small | fine trades, tiny exposure | sizing, deployment |

2025 was assumed to be the first for weeks. The trade ledger says it is the second:
**75 trades at a 45.5% hit rate — the highest hit rate of any year in the table** —
against 324 trades in 2024 and 797 in 2021. It is not a year the book lost in, it is a
year the book did not show up for. That single distinction invalidates every "fix the
losing trades" idea and makes the refusals the object of study.

*Instruments:* `tools/attribution_run.py` (won / lost / unforced / missed against every
trade that was available), `tools/ceiling.py` (what perfect hindsight would have made
under our own costs and constraints).

### 3. Measure the mechanism, not the outcome
Outcomes are a scalar and mechanisms are a distribution. A year's return cannot tell
you which gate closed; the funnel can.

*Instruments:* the **entry funnel** — `EnsembleBrain.funnel` counts, for every signal
that cleared the model's bar, whether it was vetoed (and by which module, by name),
dropped for lack of consensus, refused because the book was full, or taken.
`tools/gate_forensics.py` prints that per year and contrasts the weak years against the
ones that paid.

*Enforced:* `tests/test_entry_funnel.py` pins that clearing the counters mid-flight
cannot change an order — the funnel is measurement, never a decision.

### 4. Write the kill criterion BEFORE the run
Every queued experiment carries `judge` (how it will be read) and, where a seed is
chosen, `seed_rule` (which seed ships), both committed to the file before a single
number is measured.

This is the anti-optimism rule and it exists because this project has been burned by
its absence four separate times — three headlines built on the luckiest draw, and one
promotion bar derived from two lucky seeds that quietly blocked promotions for weeks.
The rule that came out of it: **a bar is itself a measurement and inherits the variance
of what it measures**, so it needs at least four seeds and is quoted as a median.

*Enforced:* `tests/test_promotion.py` (median-of-reseeds, no single lucky draw
promotes, the bar prefers the reproducible median over the headline).

### 5. Read the sealed year once, last, and whatever it says
2026 is never a selection input. It is opened once per adoption, after the decision
basis is already on the record, and it is reported even when the candidate failed —
hiding the forward number of a rejected build is how a project learns to fool itself.

*Enforced:* `tests/test_forward_readout.py` (selection functions never look at the
forward year; research years stop before the lock).

A note on where this nearly leaked: the first draft of `gate_forensics.py` included
2026 in its table "for shape". The seal permits a readout, but a number you look at
while choosing what to try next is an input whatever the header calls it. It was
removed, and the reason is written beside the year loop so the next person does not
re-add it.

---

## What guarantees any of this happens

A document does not. These do.

| the failure | what stops it now |
|---|---|
| a finished experiment nobody reads | `pulse.neglected()` flags it after 2h, every hour, forever |
| a row left in `failed` | same |
| a manual row nobody launched, GPU idle | same |
| the runner crashing on a manual row | `autotest.pick_queued`, and a test that CALLS it |
| a displayed number that has gone stale | `pathMatchesReturn` in the dashboard; consistency derived on read |
| a statistic that contradicts another | `gate_forensics` refuses to write a self-contradicting report; `preview/test_badge_matches_table.py` |
| an idea silently dropped | `agenda.jsonl` is append-only; killed ideas become graveyard rows with the honest result |
| a lever that does not exist | `test_every_lever_in_the_shipped_program_is_real` |
| Spanish leaking into the public page | `test_the_public_page_is_in_english` |

Two of those guards were written the day the thing they guard against actually
happened. That is the intended pattern: **a failure is not closed until the guard that
would have caught it exists.**

---

## The honest gaps

Listed because a method that only lists its strengths is advertising.

- **The pulse reports; it does not act.** Nothing relaunches a crashed manual row or
  extends an empty agenda without the agent. The watchdog keeps daemons alive, not
  research moving.
- **`test_the_queue_is_ordered_by_priority` re-implemented the picker it tested**, so
  the daemon could be wrong while the suite stayed green. Fixed here, but nothing
  systematically detects a test that copies logic instead of calling it.
- **Diagnosis is younger than the search.** The funnel is one day old and the loop has
  been running for weeks. Most of the 46 experiments on record were proposed before any
  of this existed, which is why the refutation rate is what it is.
