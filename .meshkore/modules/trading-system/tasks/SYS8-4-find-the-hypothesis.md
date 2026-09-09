---
id: SYS8-4
title: "Find the hypothesis system 08 will test, by measurement and by cluster debate"
status: in-progress
priority: high
owner: win-opus-5
category: trading-system
initiative: system-eight-from-zero
created: 2026-09-09
updated: 2026-09-09
tags: [system08, hypothesis, research, cluster, literature]
depends_on: [SYS8-1, SYS8-2]
blocks: [SYS8-3]
---

## Scope

SYS8-3 is blocked on one thing: system 08 has no hypothesis. This task is the search for
it, and it is deliberately NOT a coding task. Nothing is built until a mechanism survives.

Operator, 2026-09-09: *"antes de empezar a hacer código"* — three agents debate, read
papers and documentation, use the model's own world knowledge, and reach the most powerful
conclusion they can. Explicitly asked for: cross-domain thinking (fractals, nature, cycle
mathematics, economic-cycle theory), no tunnel vision, and originality over convention.

## The standing rule for anything proposed here

Five lines or it is not admissible. This is the protocol broadcast to the cluster:

    CLAIM / MECHANISM / TEST / KILL / COST

`MECHANISM` must name **who is on the other side of the trade and why they keep losing**.
If the loser cannot be named, the edge does not exist. `KILL` is registered before the
number is computed. `COST` is measured against a 30 bps round trip.

## Closed so far — do not re-propose

| id | what | why it died |
|---|---|---|
| R02 | H1-R, order-flow absorption / impact residual | +0.08 bps at 60m over 74,181 clustered events, 2,985 days, 9 years. Well-powered zero. |
| R02 | signed order flow at 15m generally | top flow decile = -0.01 bps at 60m, before costs |
| R03 | over-extension reversal (the mirror H1-R surfaced) | post-hoc; passed consistency (8/9 years) and monotonicity, FAILED its registered 60m magnitude test at -3.13 bps |
| — | crypto carry, short perp / long spot | published Sharpe 6.45 (2020-25) -> 4.06 from 2024 -> NEGATIVE in 2025 |
| — | liquidation-cascade recovery | third party: +2.33%/trade over 72 OOS trades, then beta decomposition — 54% BTC, alpha p=0.182 |
| — | critical slowing down as crash warning | refuted across Dow/S&P/NASDAQ/DAX/FTSE over a century; only rising variance survives, and that is volatility |
| R04 | "all crypto edges decay uniformly" (mine) | withdrawn. 86% of canonical signals decay across the full record but only 57% from 2019 on, under my own 60% line — carried by 2017-2018 |

## What survived R04, and why it matters more than the claim it killed

The decay is **not uniform**. It is concentrated in one family, and it is the family the
champion is built on:

| signal | 2017 | 2019 | 2022 | 2025 | slope | from-2019 |
|---|---:|---:|---:|---:|---:|---:|
| mom_30d | 71.6 | 16.4 | 13.4 | 10.0 | -4.19 | -3.97 |
| mom_7d | 17.8 | 9.5 | 18.1 | -3.8 | -2.50 | -3.27 |
| mom_3d | 54.7 | 11.9 | 20.1 | -7.9 | -5.26 | -3.42 |
| stretch_30d | 71.3 | 20.4 | 9.4 | 6.1 | -5.10 | -4.38 |

All four multi-day trend signals decay and keep decaying with 2017-2018 removed. mom_3d
and mom_7d are negative in 2025. The signals that IMPROVE from 2019 are short-horizon and
volume-based: mom_1d +1.14, volume_shock +2.12.

System 06 is a 60-day trend follower. Its core lever is the signal whose gross payoff fell
from 71.6 bps to 10.0 at about -4 bps a year. That reframes years of work: the decay we
attributed to our own overfitting is at least partly the ground moving under the family.

## Open, with the right question attached

- **Multifractal / generalised Hurst.** Structure is real and reproducible (H > 0.76,
  walk-forward, 2018-2025). No paper in that literature shows an out-of-sample trading
  edge. Question is not "is crypto multifractal" — it is — but **does conditioning on H
  beat conditioning on realised volatility**, which nobody ran.
- **The short-horizon family.** R04 says it is improving while trend decays. Gross payoffs
  are single-digit bps against a 30 bps round trip, so the question is whether anything
  there survives costs at all, or whether it is only a sizing/stand-aside input.

## Blocked on, and not by me

The cluster debate the operator asked for is not happening. 25 frames received from peers,
**zero characters read** — every inbound payload arrives empty. Identity was unified
(`win-opus-5`, one socket, outbox drain) and the payloads stayed empty, so the first
diagnosis was wrong. The listener now dumps raw frames to find the real fault.

## Done when

A hypothesis exists that survives the five-line test, has a named loser, and has a
registered kill criterion — at which point SYS8-3 unblocks and code begins.
