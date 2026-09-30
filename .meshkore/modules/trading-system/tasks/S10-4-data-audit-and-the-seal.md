---
id: S10-4
title: "C. Data: audit and clean the inputs 010 will train on, and verify the 2026 seal"
status: done
priority: high
owner: unassigned
profile: developer
category: trading-system
initiative: system-ten-conditioned-rl
created: 2026-09-27
updated: 2026-09-30
tags: [system10, data, phase-c]
depends_on: [S10-2]
blocks: [S10-6]
---

> Read `.meshkore/context/system10-design.md` before starting. It is the plan this task is one piece of, and it carries
> the laboratory's standing rules under "Our conditions" and the kill conditions under section 7.

## The ask

*"Limpieza de datos"*. 010 trains on the shared catalogue through 06's dataset builder; this
task makes sure what it trains on is whole, causal, and physically separated from 2026.

## What to do

1. For the 14-symbol universe at 15m, 2017-08 to 2025-12-31: gaps, duplicate stamps, zero
   or negative prices, bars whose high < low, clock alignment across symbols, and the
   listing date of each symbol (the universe is not constant: SOL/DOT 2020-08, AVAX 2020-09).
   Write `research/system10/DATA_AUDIT.md` with one table per check and the counts.
2. External series 06 consumes (Fear & Greed, funding, on-chain, FRED): confirm each carries
   a publication lag in the catalogue and is aligned point-in-time. Any series without a
   recorded lag is listed and NOT used by 010 until it has one.
3. **The seal.** Prove, with a test in `trading-system/tests/`, that `system010`'s dataset
   entry points cannot return a bar dated 2026 without `--forward`, and that the research
   loader's last stamp is at or before 2025-12-31 23:45 UTC.
4. **The feature registry.** Freeze the list of features 010's state uses (the 06 feature
   set plus the book-state fields from the design) in
   `system010_conditioned_rl/features.py` with a content hash; the audit records the hash.
   No feature is added later without a row in *What helped* or *What hurt*.
5. Fix what the audit finds only if the fix is in the catalogue loaders and is additive;
   never edit candle files by hand. A defect that needs a re-download is recorded and done
   through `quantlab_catalog`.

## Done when

`DATA_AUDIT.md` is committed with counts for every check, the seal test passes, the feature
hash is recorded, and any defect is either fixed through the catalogue or listed as open.
