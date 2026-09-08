# System 08 — open, no hypothesis yet

> ## Recursive Self Improvement
> *The maxim of this loop.*

*Opened 2026-09-08. Status: **blank**. Bar to beat: system 06's sealed 2026 **+25.71%**
at 22.13% drawdown, 90 trades.*

**What the maxim demands.** The hard half is *recursive*: the loop must improve the way
it improves, not only the strategy it improves. Every system before this one iterated on
genomes and thresholds while the **method** stayed still — and the method is what kept
failing. Three sealed readings were lost to it in one day.

So the rule that follows: when this loop loses, the first question is not *"which lever
was wrong"* but **"which gate was missing"**. A run that only produces a better strategy
has not improved the loop. A run that produces a new gate has.

## 1. Hypothesis

**None yet, deliberately.** The folder, the working gate, the documentation and the data
access are ready; the idea is not. Inventing one to fill the silence would be the worst
possible start — system 06 spent three weeks proving that a plausible idea measured badly
costs more than no idea at all.

## 2. What it is

Nothing yet. What already exists around it:

- **The data.** `import quantlab_catalog as cat` — 14 symbols of 15-minute candles back
  to 2017, perp funding, Fear & Greed, four on-chain series, eleven FRED macro series.
  Seven years of downloads already paid for. `python -m quantlab_catalog.inventory`
  prints what is there and what is not.
- **The gate.** `quantlab_system08.loop` — the working process as code rather than as
  good intentions. Seven ordered stages; a candidate that has not cleared stage N cannot
  be presented at stage N+1, and 2026 has exactly one door with three locks on it.
- **The bar.** One number, stated once, so nothing here can quietly redefine winning.

## 3. What helped

*Nothing measured yet.*

## 4. What hurt

*Nothing measured yet.*

## 5. What is still open

Everything. The first decision is the hypothesis, and it belongs to the operator.

## 6. Rules learned

Inherited, not re-derived. **Read
`trading-system/quantlab_system06/docs/SUMMARY.md` sections 4 and 6 before proposing
anything** — twenty ideas that were measured and refused, and nine rules that cost weeks.
The three that are now enforced in code:

1. 2-of-2 walk-forward exams before a sealed reading. One exam year is a coin flip.
2. Price the edge: if the per-year ratio spread against the incumbent straddles 1.0, the
   sealed year settles nothing and the reading is not spent.
3. A stage is cleared once. Re-running an exam until it passes is selection, not
   measurement.
