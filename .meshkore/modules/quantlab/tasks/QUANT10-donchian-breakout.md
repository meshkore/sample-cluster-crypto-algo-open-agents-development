---
id: QUANT10
title: "Evaluate the classic Donchian/Turtle breakout as a new hypothesis"
status: in_progress
priority: low
owner: unassigned
category: quantlab
initiative: liquid-ml-research
created: 2026-08-04
updated: 2026-08-04
tags: [hypothesis, momentum, trend-following, evaluation]
depends_on: []
blocks: []
---

## Why this exists

Following QUANT9's finding that a single undisclosed vendor script is a poor
place to look for a mechanism worth testing, the operator asked for a
deliberate search of public sources (Reddit/forums, academic literature) for
a crypto trading idea with real methodological grounding, to implement and
learn from — not for a promise of profit.

## What was found

Web search across Reddit-adjacent discussion, trading blogs, and academic
literature (arXiv 2009.12155 "A Decade of Evidence of Trend Following
Investing in Cryptocurrencies", among others) converges on the same
baseline mechanism used across that literature: the **Donchian channel
breakout**, the long side of the 1980s "Turtle Trading" system (Richard
Dennis and William Eckhardt). Unlike QUANT9's vendor script:

- The rule is exact and has been public for over 40 years — no ambiguity
  to guess at, unlike "0DTE Scalper"'s undisclosed Kalman filter.
- It is long-only-compatible by construction: secondary sources report the
  original system's short side loses money on Bitcoin, so only the long
  side is implemented here — consistent with this lab's own invariant, not
  merely convenient.
- It naturally fits this lab's default daily-bar universe (it is a swing/
  trend system by design, holding for days to weeks), so no data-scope
  override like QUANT9's was needed.

No performance claim from any secondary source is taken at face value —
same discipline as QUANT9. "Profit factor above five" and similar figures
seen during the search are marketing/blog claims, not evidence.

## What was done

Hypothesis `H-DONCH-001` in `src/quantlab/strategies.py`, family
`donchian_breakout`: long on a fresh N-bar high (default N=20), flat again
on a fresh M-bar low (default M=10, M<N is the deliberate asymmetry — exits
faster than it enters). Wired into `loop.py`'s `DEFAULT_PARAMS` and mutation
schedule (N grows with generation, M stays half of N). 6 deterministic unit
tests in `tests/test_donchian_breakout.py`, including one verified
non-vacuous by sabotage (shrinking the exit period to 1 makes a shallow
pullback that should NOT close the position actually close it, confirming
the real test would catch a regression in the asymmetry).

## Remaining

The actual Phase-1 sweep, robustness checks, forward evaluation and
benchmark comparison, run through the normal autonomous loop once merged —
this task does not close until that evidence exists and is reported, win
or lose, exactly like every other family.

## Acceptance criteria

- No claim from any secondary source (blog, forum, paper abstract) is
  reported as this lab's own evidence until our own pipeline produces it.
- The mechanism is tested exactly like any other family: no exemption from
  the drawdown limit, cost model, or benchmark comparison.
- Whatever the result, it is reported honestly.
