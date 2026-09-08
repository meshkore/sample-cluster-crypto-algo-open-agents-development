---
title: "How every trading system documents itself"
category: context
updated: 2026-09-08
owner: master
status: active
---

# How every trading system documents itself

**The purpose of this standard is one sentence: when we open a new system, its first
instruction is "read the previous systems' summaries", and that must be enough to stop
us repeating work we have already done and paid for.**

Operator, 2026-09-08: *"cuando empecemos una nueva estrategia lo primero que le vamos a
decir es lee las estrategias anteriores para ver qué es lo que ya hemos hecho y qué es
lo que no hay que repetir."*

## The folder

Every system gets exactly one documentation folder, beside its code:

```
trading-system/quantlab_<system>/docs/
    SUMMARY.md      the compressed diary — hypothesis, what was tried, what helped,
                    what hurt, what is still open. THE ONE A NEW SYSTEM READS.
    RESULTS.md      the numbers — per year, backtest and sealed forward, champion config
    context.json    the same facts, machine-readable, for the dashboard and for agents
```

Three files, no more. A folder that grows a fourth file grows a place for the important
one to hide.

## SUMMARY.md — the contract

Written for someone who has never seen the system and has ten minutes. Compressed to the
point of terseness; a reader who wants depth has the git history and the `rnd/` ledger.
Six sections, in this order, with these headings:

1. **Hypothesis** — what this system believes about the market, in three sentences. Not
   the architecture: the *claim*.
2. **What it is** — the mechanism in a paragraph, plus the data it consumes.
3. **What helped** — a table. Each row: the change, the measured effect, and the
   evidence that survived. Only things that are still in the live path or were adopted.
4. **What hurt** — a table, same shape, and **at least as long as the one above**. A
   system with no failures listed has not been documented; it has been advertised.
5. **What is still open** — questions asked and not answered, with why they stalled.
6. **Rules learned** — the transferable ones. These are the lines a future system reads
   and obeys without re-deriving.

The two tables are the heart of it. Everything else can be reconstructed from code; what
cannot be reconstructed is which of a hundred plausible ideas were measured and refused.

## RESULTS.md — the contract

Per calendar year, always in two eras, always labelled:

- **training / research** — the years the system was allowed to be fitted on
  (everything to 2025-12-31 in this laboratory).
- **sealed forward** — 2026, never optimised against, read only at adoptions and
  recorded whatever it says.

Plus: the champion configuration verbatim, the drawdown beside every return, the trade
count, and the trivial baselines the system is measured against. A percentage without
its era is not information — it is a number that could mean either of two opposite
things.

## context.json — the contract

The same facts as a machine can read them, so the dashboard's **Log** tab and any agent
can consume the documentation without parsing prose. Validated by
`trading-system/tests/test_system_docs.py`, which fails the suite when a system's
documentation is missing, malformed, or contradicts its own `SUMMARY.md` headings.

```jsonc
{
  "id": "system06",                  // matches the package folder
  "name": "The oracle-taught net",
  "status": "champion|frozen|workshop|blank",
  "hypothesis": "one sentence",
  "period": {"opened": "2026-08-18", "closed": null},
  "data": ["15m candles, 14 symbols", "..."],   // from the shared catalogue
  "helped": [{"what": "...", "effect": "...", "evidence": "..."}],
  "hurt":   [{"what": "...", "effect": "...", "evidence": "..."}],
  "open":   [{"what": "...", "why": "..."}],
  "rules":  ["transferable lesson", "..."],
  "results": {"sealed_2026": {...}, "annual": {"2018": 1.78, ...}}
}
```

## The rule about the strategy list

**One box per system, showing its best result.** Not one per backtest, not one per
variant. Five systems means five boxes. Each box opens four tabs: **Results**,
**Theory**, **Diagram**, **Log** — where Log is `SUMMARY.md`.

The reason is the one above: the list is a reading list for the next system, and a list
of forty runs is not a reading list.

## When it is written

- **A system opens**: `SUMMARY.md` gets its Hypothesis and What it is. The other four
  sections are empty and say so.
- **Every adoption or refusal**: one row is added to *What helped* or *What hurt*, in
  the same commit as the result. Not later, not in a batch — the row costs a minute
  while the numbers are on screen and costs an afternoon of archaeology afterwards.
- **A system freezes**: the summary is finished, `status` becomes `frozen`, and nothing
  in the folder changes again.
