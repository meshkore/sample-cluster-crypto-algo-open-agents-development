---
id: QUANT32
title: "System 08: build it, measure it, and put the measuring on a loop"
status: in-progress
priority: high
owner: win-opus-5
category: quantlab
initiative: system-eight-from-zero
created: 2026-09-13
updated: 2026-09-13
tags: [system08, residual-momentum, experiment-loop, sealed-2026, cluster]
depends_on: [SYS8-4]
blocks: []
---

# System 08: build it, measure it, and put the measuring on a loop

The design initiative closed and the operator authorised code. This task covers the part
after that: turning the design into a book that runs, measuring it honestly, and making the
measuring continuous instead of something a person has to sit and drive.

The operator's standing instruction for this phase is the maximum measurable result in the
minimum time, with the cluster peers doing the research legwork and this agent
orchestrating, integrating and owning the commits.

## What the system is

A beta-neutral residual momentum book on crypto perpetuals. Rolling causal loadings, the
residual ranked cross-sectionally, inverse-residual-volatility sizing, a BTC hedge for
whatever net loading remains, and costs and funding charged explicitly.

## What has been measured, and what it says

Five numbered cycles exist. Each is a research backtest to 2025 followed by ONE sealed 2026
read, recorded whether the result was liked or not.

| cycle | configuration | research | Sharpe | sealed 2026 |
|---|---|---|---|---|
| 1 | 14 names, BTC factor, untuned | +511.6% | 0.78 | **+7.5%** |
| 2 | 14 names, 54-config sweep | +108.6% | 0.44 | **+7.3%** |
| 3 | 32 names, BTC factor | +311.9% | 0.81 | **-5.6%** |
| 4 | 32 names, market-ex-self factor | +374.8% | 0.91 | **-7.1%** |
| 5 | 32 names, market factor, seasoned | +143.6% | 0.57 | **-6.9%** |

**The pattern is the finding.** Every change that improved the research years left the
sealed year unchanged or worse, monotonically, across five cycles. Cycle 4 is the best
backtest this system has produced and the worst forward read. Nothing clears the t > 3
hurdle and nothing has been adopted.

Comparing cycle 1 with cycle 3 isolates the variable: same factor, same configuration, only
the cross-section differs, and the sealed year changes sign.

## What worked, and what did not

**Worked.** The market factor. Residualising against the equal-weight cross-section with
each name excluded from its own basket, rather than against BTC alone: Sharpe 0.809 to
0.907, t 2.33 to 2.61.

**Did not, all measured and all recorded with their numbers in
`research/system08/experiments/`:**

- *Funding as an edge.* Between -0.4% and +0.4% of equity in eight of nine years. The
  design leaned on structurally positive funding paying the short leg. It does not, at this
  size. Removed from the thesis.
- *Partial adjustment* (Garleanu-Pedersen). Cost falls almost exactly proportionally and
  return falls faster. The cost is the price of the signal, not waste.
- *A liquidity screen.* Trading only the large names destroys the edge monotonically -
  Sharpe 0.91 on all names, 0.14 on the top eight. Inside a universe already screened at
  USD 10M daily turnover, breadth beats size.
- *Volatility targeting* (Barroso-Santa-Clara). Our best year has the highest realised
  volatility and the bad years sit mid-range, so the overlay cuts the good year and cannot
  see the bad ones coming. **Our failure mode is direction, not volatility** - which rules
  out a family of fixes rather than one of them.
- *Seasoning as the explanation for 2026.* Requiring a year of listing history does exactly
  what the hypothesis predicted to the backtest (total down, year profile far more even,
  seven positive years of nine) and nothing at all to the sealed year.

## The loop

`research/system08/loop.py` runs queued hypotheses from `program.jsonl` forever, on
research years only. It enforces what a person would otherwise have to remember: 2026 is
never read here, trials accumulate on disk across restarts, consistency ranks above the
headline, every result is written including the bad ones, and nothing is ever adopted by
the daemon.

## Acceptance

- [x] The book runs end to end and its causality is asserted rather than trusted.
- [x] Numbered cycles carry both eras to the live page, good or bad.
- [x] Every rejected idea is recorded with the numbers that rejected it.
- [x] The experiment queue runs unattended and cannot reach the sealed year.
- [ ] A configuration that is positive in every calendar year of the research era.
- [ ] A sealed read that is positive on a configuration differing STRUCTURALLY from the
      five already spent - not on another point of research Sharpe.
