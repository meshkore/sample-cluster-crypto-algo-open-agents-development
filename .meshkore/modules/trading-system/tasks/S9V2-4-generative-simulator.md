---
id: S9V2-4
title: "The generative simulator: every group's moves, every day, without reading the tape"
status: active
priority: high
owner: win-opus-5
category: trading-system
initiative: system-nine-reality-alignment
created: 2026-09-14
updated: 2026-09-14
tags: [system09, v2, behaviour, clearing, agents, macro]
depends_on: [S9V2-1, S9V2-2]
blocks: [S9V2-5]
---

## The change of shape, and why it is the whole of v2

The operator, 2026-09-14: *"tú tienes que hacer un modelo que simule la realidad del mercado
… irás simulando lo que hacen todos los actores que no somos nosotros … qué hará cada grupo
cada día y cuáles son los movimientos de dinero y a qué assets … queremos llegar al máximo
detalle ahí para poder hacer una simulación real."*

v1 solves the **inverse** problem: the tape is given, and the model infers who must have
traded to produce it. That is why it cannot answer a forward question - take the tape away
and nothing moves. Its flows are conserved, its float is calibrated to 0.00%, and it still
cannot say what tomorrow looks like, because tomorrow's tape is the input it no longer has.

v2 solves the **forward** problem. Three pieces, in this order:

1. **The behaviour model (L2).** For each day, each cohort, each asset: how much does this
   group buy or sell, and how much cash does it move in or out? Learned from eight years of
   reconstructed flows rather than asserted as Brock-Hommes constants. This is the piece that
   replaces "the tape says so" with "this group does this".
2. **Clearing (L4).** The cohorts' desired flows meet each other and a price comes out. Until
   this exists there is no simulation, only a replay - v1 takes every price from the tape.
3. **The world (H).** Behaviour is a function of more than price history: liquidity, rates,
   inflation, the dollar, commodities, the news and the regulatory calendar. The operator has
   asked for this repeatedly and it belongs HERE, as an input to behaviour, not as extra
   columns bolted onto a return forecast.

Trading is downstream of all three, and that ordering is the point. If the simulator is
right about what everyone else will do, the trade is the easy part; if it is wrong, no
trading policy rescues it - which is exactly what the policy study measured (24 candidates,
none beat holding the universe in every research year).

## The first measurable step, which is where this task starts

**Predict cohort flow, and score it against the reconstruction.** For every (day, cohort,
asset) the reconstruction already knows the realised net flow. So:

- Build the flow dataset from `Trajectory.state` - net units per cohort per asset per day,
  and the cash that moved with it.
- Fit a model that predicts tomorrow's flow per cohort from today's state: holdings, dry
  powder, unrealised P&L, how long it has been holding, recent price action, funding.
- Score it **walk-forward, by cohort**: rank correlation and sign accuracy of predicted
  against realised flow. Per cohort, because "the market's flow" is an average that hides
  the thing worth knowing - long-term holders and momentum traders are supposed to disagree.

That score is the first honest measurement of whether this system knows what participants do.
It is not a P&L, it cannot be flattered by position sizing, and it can be computed on the
research years alone.

## Done when

- `python -m system009_participant_ledger.behaviour` prints a per-cohort table: rows of flow IC and sign
  accuracy, walk-forward, research years only.
- A cohort whose flow cannot be predicted better than its own persistence is named as such.
- The result decides whether clearing is worth building: a simulator whose agents' actions
  are unpredictable will produce a plausible-looking market that means nothing.
