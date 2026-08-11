---
id: QUANT15
title: "Four-piece system: a market-wide major-trend detector and three regime-conditional strategies"
status: in_progress
priority: high
owner: unassigned
category: quantlab
initiative: liquid-ml-research
created: 2026-08-05
updated: 2026-08-05
tags: [architecture, regime, cycles, money-management, measurement]
depends_on: [QUANT12, QUANT14]
blocks: []
---

## What the operator asked for

A system in four separable pieces rather than one rule: a **major-trend
detector** that says which market we are in, and **three strategies** — one for
bull, one for sideways, one for bear — each tunable on its own, with the
detector operable and improvable independently. The reasoning: crypto moves in
clear cycles, we have lived through three or four of them, and if we can name
the cycle we are in we have already won half the problem. Bear markets should
be traded by chasing the rebounds; bull markets by riding the peaks and
scaling out.

The architecture was built as asked. The premises behind the branch contents
were measured first, and two of them did not survive.

## The four pieces, as built

| Piece | Where | What it does |
|---|---|---|
| Major-trend detector | `src/quantlab/regime.py` | Labels every bar BULL / SIDEWAYS / BEAR / UNKNOWN from a fixed six-asset reference basket. No strategy, no position, no view of the traded candidate. |
| Bull branch | `regime_system._BullTrendBranch` | H-SMARSI-001 verbatim — the lab's only rule with a positive walk-forward record. |
| Sideways branch | `regime_system._SidewaysBreakoutBranch` | 20-bar breakout, exiting at the channel midpoint. |
| Bear branch | `regime_system._BearParticipationBranch` | Confirmed counter-trend advance only. Explicitly **not** a dip-buyer. |
| Router | `regime_system._RegimeRouter` | Family `regime_router`. One branch live at a time, flat for one bar at every handover. |

The detector is a deliverable on its own: `quantlab regime` prints the episode
history and the label scorecard without running a backtest.

## What the measurement said before any of it was tuned

**1. The detector identifies the bad regime and not the good one.** Forward
20-bar return of the composite, conditional on the label known that bar,
2017-2025:

| label | bars | mean forward return |
|---|---|---|
| BEAR | 794 | +1.27% |
| BULL | 1,316 | +2.64% |
| SIDEWAYS | 691 | +4.32% |

BEAR is reliably the worst bucket. But SIDEWAYS outranks BULL, which is the
signature of a lagging trend call: the BULL label arrives late enough to
collect the end of advances. The detector's honest claim is "this is a bad
time", not "this is the top".

**2. Chasing rebounds in a bear market is the worst available idea.** Mean
forward return on days each tactic was long, pooled over the six reference
assets, bucketed by regime:

| tactic | BEAR | SIDEWAYS | BULL |
|---|---|---|---|
| buy and hold | +1.77% | +5.81% | +3.76% |
| trend (20 over 50) | +4.39% | +4.06% | +5.93% |
| 20-bar breakout | +3.97% | **+10.94%** | +10.06% |
| RSI < 30 bounce | **-0.20%** | +4.76% | +2.26% |
| 5% single-bar drop | **-0.17%** | +5.65% | +4.80% |

Buying weakness is negative in a bear regime and solidly positive in the other
two. A bear market is a sequence of failed bounces and a rule that buys all of
them is buying the failures. H-REGIME-001 (QUANT12) used exactly that bear
bounce and returned -8.46%; this is why. The bear branch was therefore built to
buy confirmed strength cautiously, against the original instruction, on this
evidence.

**3. Regime does not select the tactic.** The 20-bar breakout is the strongest
cell in both SIDEWAYS and BULL. What the regime separates is *magnitude*, not
*which rule to use* — which makes the honest role of the detector exposure
governance rather than strategy switching.

## Result: the router loses to the single rule it routes to

Phase-1, pre-2026, five-asset hourly basket (332,225 bars), one shared capital
pool, identical costs and money management across every arm — the QUANT14
stage-6 policy (exit 0.35 / sizing 0.10 / cap 0.10), the only configuration
measured legal at this scope.

| arm | return | max DD | trades | avg exposure | in market | return / exposure |
|---|---|---|---|---|---|---|
| **control** — H-SMARSI-001, no regime | **+432.4%** | 19.05% | 1,282 | 11.4% | 58.9% | 37.9 |
| control gated to BULL+SIDEWAYS | +368.3% | 19.03% | 1,051 | 9.3% | 44.2% | **39.6** |
| **regime_router** (weights 1.0/0.6/0.3) | +211.2% | 20.16% | 2,373 | 8.3% | 44.2% | 25.4 |
| control gated to BULL only | +177.5% | 18.99% | 765 | 6.7% | 29.9% | 26.7 |
| regime_router, all weights 1.0 | +146.0% | 22.90% | 1,552 | 4.6% | 25.1% | 31.7 |

**Every regime-aware arm is worse than the plain rule.** The router gives up
221 percentage points to the control and does not buy a single point of
drawdown back — 20.16% against 19.05%. That is the finding that matters: the
regime call removed return without removing risk, which is the one trade a
risk governor is supposed to make in the other direction.

The decomposition separates two distinct failures:

- **Branch switching destroys efficiency.** The router earns 25.4 per unit of
  exposure against the control's 37.9. The sideways and bear branches are
  simply worse rules than the one they replace, so every hour spent in them is
  an hour of worse trading. Switching is not free even when the switch is right.
- **Filtering is efficiency-neutral and therefore pointless.** Gating the
  control to BULL+SIDEWAYS returns 39.6 per unit exposure against 37.9 — within
  noise. The filter does not concentrate return into the good regimes, it just
  subtracts 25% of the time in market and 15% of the return along with it. If
  the labels carried exploitable information, this arm is where it would show,
  and it does not.

Not promoted. Nothing here is proposed for the champion ledger.

## The honest limits of this result

- **The control is tuned and the router is not.** H-SMARSI-001's parameters
  were selected on this exact scope in QUANT13; every branch here runs on
  conventional defaults. This is the strongest argument in the router's favour
  and it is a real one. What it does not explain is the drawdown: tuning moves
  returns, and the reason to accept less return was risk reduction that never
  appeared.
- **The cycle sample is 2 to 3, not 3,059.** The daily history covers
  2017-08 to 2025-12: two clean tops (2017-12, 2021-11) and two clean bottoms
  (2018-12, 2022-11). A rule that classifies *cycles* has that many independent
  observations no matter how many bars it sweeps. Any future search over the
  detector's own parameters is fitting a handful of events and must be read
  that way.
- **The reference basket is survivorship-biased.** All six assets are still
  listed today, so the composite describes the market's survivors and tilts
  slightly toward BULL.
- One basket, one interval, pre-2026 only. The 2026 forward window is untouched.

## Round 2 (2026-08-05): Kotegawa, the drawdown budget, and the research pool

### Kotegawa's deviation rate — the rule is real, the capacity is not

Operator asked to explore Takashi Kotegawa (BNF). His actual signal is the
25-day moving-average **deviation rate**: buy 20-35% *below* the 25-day
average, exit on reversion toward it. That is not the RSI-30 dip this
laboratory already rejected — it is one to two orders of magnitude more
extreme, a capitulation filter rather than a pullback filter, and it had never
been measured here. Forward return from the -35%..-25% band, by regime:

| | BEAR | SIDEWAYS | BULL |
|---|---|---|---|
| hourly, +120 bars | -1.57% (n=2,463) | +5.21% | **+10.13%** (n=1,310) |
| hourly, +480 bars | -0.60% | **+18.44%** (89% win) | +13.86% |
| daily, +20 bars | +2.16% (n=141) | +14.04% | -1.99% |

**A twelve-point spread decided entirely by the regime label.** This is the
first and only evidence in this task that the detector carries exploitable
information — every earlier tactic was ranked the same way in every regime.
It also confirms the bear finding rather than overturning it: even his much
stronger signal is flat-to-negative in a bear market, at every horizon, on
2,463 observations. A 30% drop in a bull market is a dislocation; the same
drop in a bear market is the trend.

At portfolio level, though, it does not carry:

| arm (5-asset hourly) | return | max DD | trades | exposure | ret/expo |
|---|---|---|---|---|---|
| control | +432.4% | 19.05% | 1,282 | 11.4% | 37.9 |
| router, deviation in sideways | +166.4% | 20.66% | 1,654 | 7.3% | 22.7 |
| router, deviation in bull (-0.20) | +91.8% | 20.95% | 1,211 | 2.4% | **37.7** |
| deviation standalone (-0.25) | +68.8% | 20.89% | 164 | 1.9% | 36.5 |

The diagnosis is capacity, not edge. **Per unit of deployed capital the
deviation rule matches the control** (37.7 and 36.5 against 37.9) — it simply
deploys almost nothing, because a 25% collapse below the 25-day average
happens 164 times in nine years across five majors. Kotegawa was not trading
five names; he scanned the whole Japanese market for whichever handful had
capitulated that week. Widening to the 304-asset daily universe did not rescue
it either (+67.2% at entry -0.30, and it tripped the abort): the liquidity
floor and the 12-position cap bind long before breadth helps.

So the honest verdict is that this rule wants a universe this laboratory does
not currently trade — hundreds of liquid names, small positions, many
simultaneous events — and that is a scope question, not a signal question.

### The drawdown budget: raised to 30%, and it changed almost nothing

Recorded as its own decision, [[2026-08-05-drawdown-budget-and-deleverage-split]].
`maximum_drawdown` was doing two jobs — the abort threshold *and* the far end
of the de-leverage ramp — so raising it would silently have enlarged every
position as well. `drawdown_deleverage_end` is now separate and defaults to
the old coupled behaviour, so no stored policy moved.

With the two separated: **raising the abort alone is bit-identical to not
raising it** (+166.37% either way). Nothing at this scope was ever hitting the
limit. The whole effect is the gentler ramp, worth +3.2 points on the router
and +1.5 on the control's +432% base. The drawdown ceiling was not the
constraint.

### Added to the autonomous pool, with the reasoning stated

The earlier decision to withhold it was queried, and reversing it is right for
a reason worth recording: the router's losing result is an **untuned** result,
and the research loop is the machine that tunes things. Keeping it out
guaranteed it would stay untuned, which is a self-fulfilling verdict. It is
now a full member — `H-ROUTER-001` in `initial_hypotheses`, defaults in
`DEFAULT_PARAMS`, and a mutation rule that moves the deviation entry threshold
**one parameter at a time**, because moving several at once in a routed system
means a better number cannot say which of the four pieces earned it.

`loop.py` now builds the context that stage needs. Its regime is derived from
the same synthetic series the stage trades, not from the real basket: that
stage is a smoke test on synthetic data, and telling a synthetic price path
what the real market's 2021-2024 regime was would be strictly worse than
useless. The real regime call happens in Phase 1, on the real basket.

### Published to the laboratory record: S00851

Registered and evaluated through the identical `register_strategy` /
`create_experiment` / `HistoricalUniverseEvaluator` path every other published
strategy uses — no fabricated rows. **S00851, regime_router, Phase-1 pre-2026
five-asset hourly: +169.58%, 20.92% max drawdown, 1,683 trades, 7.5% average
exposure, walk-forward profitable in 6 of 12 folds (consistency 0.50, median
score -0.064).** Contrast against the control: **-264.3 points**.

It is visible on the monitor as the current strategy with its full trade
ledger, and `best_phase1` correctly still reports S00848 at +350.09% — the
high-water mark did not move, because the router did not beat it. That is the
point of putting it on the UI: the dashboard now carries the disconfirming
evidence rather than a claim about it.

## Deliberately not done

- ~~**The family is not in the autonomous research pool.**~~ **Reversed on
  2026-08-05 at the operator's instruction** — see round 2 above. The original
  reasoning (do not spend compute mutating a mechanism measured to
  underperform) was answered by the better one: the measurement was of an
  untuned configuration, and withholding it from the loop guaranteed it stayed
  that way.
- **No parameter search.** The select-at-deployment-scope decision governs any
  future sweep: it runs on the full five-asset basket at its declared interval,
  and the 25% abort is a constraint on the search, never a parameter in it.
- **No global policy change**, no historical result restated.

## Independent Codex branch (2026-08-11)

Branch `blackmac-codex-volume-rsi-regime` added three immutable iterations of a
second, deliberately small interpretation using only liquid-universe moving-
average breadth, RSI timing and relative-volume confirmation.

- `H-CODEX-VRMA-001` was refuted before forward evaluation: -21.41% in
  development and -24.46% in the 2022–2025 holdout.
- `H-CODEX-VRMA-002` returned +110.56% in development and +2.09% in holdout,
  but its no-throttle control returned -7.75%; the apparent edge was rejected
  as path-dependent.
- `H-CODEX-VRMA-003` retained the one positive branch and made cash the
  explicit SIDEWAYS and BEAR decision. It passed the no-throttle historical
  gate (+75.43% development, +10.14% validation; 13.16% and 13.64% drawdown),
  then returned exactly 0.00% on its one locked 2026 run because no BULL regime
  was confirmed. It preserved capital but failed the profit objective.

All runs used 386 candidate symbols, the causal USD 10M turnover gate, 10 bps
commission, 5 bps slippage and next-open fills. The complete forward record is
public under backtest `b791e655b034b8fe`; no 2026 observation changed a rule.

## Acceptance criteria

- The detector is causal by construction and proved so: labels computed on a
  truncated history match the full history at every one of 64 cut points, and
  a label is withheld until its own bar has closed. Both properties are
  sabotage-verified — three deliberate lookaheads were introduced and each one
  failed the suite.
- The router refuses to build without a `MarketContext` rather than falling
  back to a single rule.
- Every regime weight clears the policy's `minimum_confidence` floor, so no
  branch is silently deleted.
- The result is reported as run, against the control, whatever it says.
