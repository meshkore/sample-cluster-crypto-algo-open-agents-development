---
id: intraday-second-system
title: "A second trading system: 15-minute bars, short-horizon reversion"
status: active
priority: high
oneliner: "Build a second, independent trading system on 15m candles whose edge is a liquidity premium rather than a directional bet, so it can be measured in any market cycle."
modules: [trading-system, quantlab, tests]
target: "continuous"
created: 2026-08-12
updated: 2026-08-12
owner: unassigned
related: [liquid-ml-research, global-market-trend]
---

## Why this exists

Everything this laboratory has measured lives on daily candles, and the whole
of it inherits one property: the mechanism needs a multi-week move to pay for
itself, so in a falling market the honest answer is to hold cash. QUANT16 is
the clearest statement of it — the detector called BEAR eleven days before the
sealed window and held it through 100% of 2026, and the best a long-only daily
system could do was lose slightly less than the market. That is a correct
result and a structural ceiling. **A daily system has roughly 2,200 decisions
per asset in nine years; there is no amount of skill that turns that into an
edge measurable inside seven months.**

The operator's proposal is to attack the ceiling from the other side: raise the
resolution instead of improving the rule. At 15 minutes the same nine years
carries 96× the bars, a seven-month forward window holds ~21,500 bars per asset
rather than ~215, and a mechanism that captures a few tenths of a percent can
be tested to significance in weeks instead of decades.

The catch is stated up front, because it is what decides whether any of this
works: **costs do not shrink with the bar.** A round trip is 10 bps commission
plus 5 bps slippage per side — 0.30% of notional — and at daily resolution that
is noise against a 6% swing while at 15m it is most of the move. So this system
is not "the daily system, faster". It is a different economic claim, and the
cost hurdle is a first-class part of the entry rule rather than an accounting
detail applied afterwards.

## The claim under test

**H-INTRA-001 — short-horizon liquidity provision.** When a 15-minute candle
closes near its low after an outsized move away from the short-term VWAP,
market orders have just consumed the resting bids. Reversion over the following
few bars is the compensation for replacing that liquidity. If that is the real
mechanism, then:

1. the edge is **cycle-agnostic**, because it is paid by impatient traders in
   any market, not by drift — this is exactly the operator's intuition and it
   is a testable prediction, not an assumption;
2. it is **small per trade and frequent**, so it must be measured against the
   cost hurdle, not against buy-and-hold;
3. it should **die in genuine crashes**, when there is no inventory to be
   rebalanced and the move is information rather than liquidity — the one
   filter the design is entitled to assume.

Prediction 1 is what makes the hypothesis worth the work, and it is also what
kills it if false: results are reported per regime block, and a mechanism that
only pays in bull blocks is the daily system again in an expensive disguise.

## What separates this from the four-piece system

Nothing is shared except the contract. `trading-system/quantlab_trading/`
(System Four — detector, branches, router, policy) is untouched; the new
package `trading-system/quantlab_intraday/` imports only the tick contract, the
brain registry and the money-management protocol. Neither system can change the
other's result, which is the same property `CONTRACT.md` gives the instrument.

## Task plan

- #TRADE1 complete — the system is built, tested and measured, and H-INTRA-001
  is **refuted**. `trading-system/quantlab_intraday/` (eight modules, 32
  sabotage-verified tests, layering enforced) runs both phases against five
  majors at five intervals. The signal is real and too small: at a one-bar
  horizon a qualifying bar returns +0.034% against a +0.002% unconditional
  drift — 17x — and the round trip costs 0.30%. Of 225 populated cells in the
  displacement x close-position x horizon x era map, **two are positive net in
  both eras**, both at a 24-hour horizon and both below the +0.235%
  unconditional drift over the same day. Eight blocks 2017-2025: 0 of 7 positive,
  2,350 trades. Sealed 2026: **−24.18% over 921 trades at 24.35% drawdown**,
  consistent with training rather than diverging from it. The decomposition is
  the result worth keeping: pre-cost the blocks are a coin flip (3 of 7
  positive) and **the toll alone is 8-18% of capital per 52-day block** —
  `toll = round trips x position size x 0.30%`. The cycle-agnosticism claim is
  refuted directly by the year-by-year breakdown: at 5m the net is +1.40%
  (2017), −0.28% (2018), +0.93% (2021), −0.57% (2022), −0.08% (2025), and the
  whole positive result belongs to one asset (SOL +0.388% against BTC +0.066%).
  A liquidity premium paid by impatient traders in any market does not track
  the cycle like that.
- **An instrument fix that outlives the hypothesis.** The first resolution scan
  reported 5m at +0.193% net with **t = 6.7**, which would have justified
  building a system around it. It is an artifact of overlapping observations:
  at a 288-bar horizon on 5-minute candles one day's move is counted up to 288
  times, so the standard error divides by a sample size that does not exist.
  `edge.scan` now reports the same observations thinned to non-overlapping
  windows -- **−0.098% at t\* = −1.4** -- which also removes a clustering bias
  that had been weighting the average by how excited each period was. With
  honest error bars every interval from 5m to 4h is negative at its own best
  horizon. Any study in this repository that samples a long horizon densely has
  the same exposure.
- #TRADE2 in progress — H-INTRA-002, the direction TRADE1's numbers actually
  point at. Reversion's upside is capped by construction (price returns to the
  anchor and the trade stops), so its mean is bounded near the toll however good
  the win rate. Breakout and volatility-expansion rules at the same resolution
  have an uncapped right tail, where a 35% win rate can clear a fixed toll that
  a 60% win rate cannot. The hurdle was stated in advance and never moved:
  **0.30% gross per trade**.
- **Fourteen mechanisms, measured before anything was built.** `survey.py`
  scores candidate rules against the toll in one pass over 4.3M bars. At 1h-24h
  horizons **not one of fourteen beats drift after costs in either era**, the
  published intraday-momentum rule included — which is not a contradiction of
  the literature but a restatement of it, since those papers report breakeven
  costs of 3-10 bps and this laboratory models 30. The survey prints a `be bps`
  column so that comparison is explicit rather than implied.
- **The one that separates, at 72 hours.** At 06:00 UTC, when the day is already
  up 1.5%, buying and holding three days earns **+0.126%** over drift in
  2017-2022 and **+0.543%** in 2023-2025, net of the toll, on non-overlapping
  windows. Monotone in the entry threshold in both eras, positive on all five
  symbols in both, breakeven 72.7 bps. The dose-response is the evidence; the
  t-statistics (0.4 discovery, 1.6 validation) are weak and are quoted as weak.
- **The design rule TRADE1 predicted, confirmed by measurement.** Six portfolio
  variants over eight 90-day blocks, identical entries throughout: a trailing
  stop is worse than a stop (−0.89% vs +0.55% per block) and a stop is worse
  than none (+4.24%). Truncating the winner costs money, exactly as an uncapped
  right tail predicts. A 30-day trend filter, justified in advance by
  Moskowitz/Ooi/Pedersen rather than by the block that lost, cuts the worst
  block from −21.9% to −11.2%. The published configuration keeps both and is the
  only one of the six whose mean survives deleting its own best block.
- **Both halves are on the monitor and the 2026 one leads it.** Sealed window
  **+5.05%** net, 7.88% drawdown, 24 trades, in a year the market fell 22.6% —
  ahead of the previous champion at +1.89%. The pair was published through
  `orchestrator-manager/scripts/publish_intraday.py`, which takes the same
  parameters for both phases and sets `trade_from` itself, so the two halves
  pair structurally rather than by anyone remembering to keep them identical.
- **The finding that outlives the hypothesis: block statistics cannot see a
  drawdown that accumulates.** The training half, run continuously from 2018,
  reached +168% by May 2021 and was then **stopped by the 25% mandate on
  2022-04-08** having given back a quarter of its peak — so it never traded
  2022-2025. The eight blocks each restart at 100,000, so the worst any of them
  could report was a 17.31% within-block drawdown. Blocks answer whether a
  mechanism survives different tape; they say nothing about the path a real
  account takes through all of it. Every block table in this repository should
  be read with that limit attached, and the next configuration on this mechanism
  needs a portfolio-level de-risk rather than only per-trade sizing.
