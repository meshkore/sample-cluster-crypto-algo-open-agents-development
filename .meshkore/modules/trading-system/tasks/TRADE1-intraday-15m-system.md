---
id: TRADE1
title: "A second trading system on 5-minute candles, independent of the four-piece one"
status: in_progress
priority: high
owner: unassigned
category: trading-system
initiative: intraday-second-system
created: 2026-08-12
updated: 2026-08-12
tags: [intraday, 15m, mean-reversion, money-management, hypothesis, costs]
depends_on: []
blocks: []
---

## Scope

A new package `trading-system/quantlab_intraday/`, beside `quantlab_trading/`
and importing nothing from it except the contract (`runner.Decision`, the brain
registry, the money-management protocol). System Four keeps every file it has;
no result already recorded can move.

What the package owns:

- `dataset.py` — 15-minute bars through the backtester's own `FocusedDataset`,
  so the cache lands at `data/{research,forward}/processed/binance/<SYM>/15m/`
  and the 2026 lock is enforced by the same code as everywhere else. Adds the
  block sampler: fixed-size windows (default 5,000 tradable bars) drawn across
  the whole history so the mechanism is scored in bull, bear and chop rather
  than in whichever 52 days happen to precede the lock.
- `microstructure.py` — the entry vocabulary at 15m, and the cost hurdle.
- `context.py` — the crash/volatility filter and the optional trend gate.
- `reversion.py` — `IntradayReversionBrain`, registered as `intraday-reversion`.
- `moneymanagement.py` — `IntradayMoneyManagement`: concentrated, ATR-sized,
  with a time stop counted in BARS (the engine's is counted in days, which
  cannot express "get out after four hours").
- `launch.py` — paired runs, identical parameters except `trade_from`.

## Why the shape is what it is

**Costs, not the signal, are the binding constraint.** 30 bps round trip
against a mean 15m range of roughly 30-60 bps on BTC means a rule that fires
on every oversold bar loses by construction. The entry therefore carries an
explicit hurdle: the displacement being bought must exceed a multiple of the
round-trip cost, in the bar's own ATR units. This is the same failure the
laboratory already recorded once (`minimum_position_fraction`, the ledger with
a quarter of its trades closing for under fifty cents) arriving through a
different door.

**The time stop belongs to the brain.** `MoneyManagement.maximum_holding_days`
is in days. At 15m the horizon this mechanism claims is 4-8 hours, so the brain
counts bars itself and closes on its own clock. The policy field is left at
`None` so nothing about the stored-policy contract changes.

**5,000 bars is a window size, not a training set.** The operator's cap keeps a
run to ~52 days of tape. That is one market condition. Used alone it would fit
the mechanism to whatever mood preceded the lock, so the same 5,000-bar window
is walked across the full history and reported per block — which is also the
only way to test the cycle-agnosticism claim rather than assert it.

**Liquidity in the right unit.** The charter's floor is $10M of *daily* quote
turnover. Divided across 96 bars a day, the per-bar floor is ~$104k, and the
gate is written that way so the invariant is honoured rather than accidentally
made 96× stricter.

## Definition of done

- The package runs end to end against the real 15m cache, both phases.
- Tests: every "it did not trade" assertion has an open-gate control that must
  trade; each is sabotage-verified before it is trusted.
- `check_layering.py` knows about the package and passes.
- A first measurement is recorded honestly, whatever it says, including the
  per-block breakdown and the average trade size in money.

## Result — 2026-08-12

**Built and measured. H-INTRA-001 is refuted, and the refutation is more useful
than the strategy would have been.**

Delivered: `trading-system/quantlab_intraday/` (eight modules), 59 tests in
`trading-system/tests/test_intraday_{signal,brain,dataset,edge,wire}.py` —
seven mutations applied and all seven caught, including entry-at-the-close
lookahead and the removal of the overlap thinning — the package README as the
design record, `trading-system/README.md` naming the two systems, and
`check_layering.py` extended so the two systems structurally cannot import each
other's decisions. **563 tests pass across all three suites** and layering is
clean; nothing System Four owns was touched.

Data: five USDT majors at 5m/15m/30m/1h/4h, ~1.4 GB, cached through
`FocusedDataset` at `data/{research,forward}/processed/binance/<SYM>/<int>/`.

**The measurement, in one line: the signal carries real information worth about
a tenth of what it costs to act on.**

- Signal study, 1.33M bars: at a one-bar horizon a qualifying bar returns +0.034%
  against an unconditional +0.002% — 17x the drift, exactly where the liquidity
  story predicts it. Net of the 0.30% round trip that is −0.266%. At 96 bars the
  gross reaches +0.201% and the drift is +0.166%: by the time the move is big
  enough to pay, the information is gone.
- Bucketing by displacement is monotone: net improves from −0.31% at 1 ATR to
  −0.05% at 4-5 ATR, and does not reach zero at any depth that fires often
  enough to matter. Of the 225 populated cells in the displacement x
  close-position x horizon x era map, **two are positive net in both eras**,
  both at a 24-hour horizon in the deepest-dislocation column: +0.180%/+0.001%
  and +0.314%/+0.046% (discovery/validation), against an unconditional 24-hour
  drift of +0.235%. Both survivors are below what buying at random and holding
  a day returned. The map is kept at
  `research/agent_runs/intraday/displacement-map.txt`.
- Resolution scan, 5m to 4h, 4.7M bars. The first pass reported **5m at +0.193%
  net with t = 6.7** -- a result that would have justified building a system
  around it. It is an artifact, and finding that is the most valuable thing in
  this task. At a 288-bar horizon on 5-minute candles one day's move is counted
  by up to 288 overlapping observations that are nearly the same number, so the
  standard error divides by a sample size that does not exist. `edge.scan` now
  reports the same observations thinned to non-overlapping windows: 5,077 of
  them, **−0.098% at t\* = −1.4**.
- Thinning also removes a larger bias. Signals cluster -- 11,093 of the 5m
  signals are in 2021 against 8,167 in 2022 -- so averaging over every signal
  weights by how excited each period was. One position per day is what could
  actually be held, and on that basis the 5m gross falls from +0.493% to
  +0.202%, BELOW the +0.223% earned by buying at random and holding a day.
- With honest error bars **every interval from 5m to 4h is negative at its own
  best horizon** (net\* −0.098% to −0.200%, t\* −0.8 to −2.8), and every best
  horizon is 24 hours rather than the few hours the mechanism claims.
- The cycle-agnosticism claim -- the entire reason to build this system -- is
  refuted directly. 5m net by year: +1.40% (2017), −0.28% (2018), +0.93%
  (2021), −0.57% (2022), +0.26% (2024), −0.08% (2025); the sign tracks the
  cycle. By symbol the whole result is one asset: BTC +0.066%, ETH +0.065%,
  SOL +0.388%.
- Eight blocks 2017-2025: 0 of 7 tradeable blocks positive, −7.9% to −16.8%,
  2,350 trades, win rates 51-62%. Forward 2026: **−24.18% over 921 trades at
  24.35% drawdown** — consistent with training rather than a disagreement.
- The decomposition is the finding: pre-cost the blocks are a coin flip (3 of 7
  positive, mean −0.4%) and **the toll is 8-18% of capital per 52-day block**.
  `toll = round trips x position size x 0.30%`, which is the design equation
  for anything traded at this frequency here.

Two defects the work surfaced, both fixed and both regression-tested: the
laboratory's `risk_per_trade` is meaningless at intraday stop distances (every
position clamps to the cap and the ATR scaling never operates), and
`FocusedDataset` requires a timezone-aware lock string or it raises deep in the
loader with an error that reads as a broken checkout.

## Settled on 5 minutes — 2026-08-12, operator decision

The timeframe study was a detour. The system is a **5-minute** system: one
interval, `INTERVAL = "5m"`, `bars_per_day = 288`, twelve 5,000-bar blocks, a
four-hour time stop of 48 bars, and the volatility window expressed in DAYS so
it means the same thing if the interval is ever changed from the command line.

Two things were added so iterating is cheap rather than ceremonial:

- **`prepare.py`** — one idempotent command that downloads the candles for both
  eras and computes and stores the indicator panel for every window a run will
  ask for. `IndicatorStore` under `data/indicators/5m/`, keyed on a digest of
  the candles, so a stale panel is discarded rather than served.
- **`launch.py --brain <name>`** — the harness is no longer bound to
  `IntradayReversionBrain`. A new hypothesis is a file with `@register` and a
  launch by name, measured through the identical blocks, costs, sealed window
  and cost decomposition, which is the only reason two of them are comparable.

Verified end to end at 5m on BTC/ETH/SOL: `prepare` warmed 32 panels over 12
windows, and a full 12-block run then took 73 seconds. Result unchanged in
character -- 1 of 12 blocks positive, mean −6.5%, 1,296 trades, and pre-cost
several blocks are positive while the toll takes 3.5-13% of capital per block.

## What this licenses next

1. The hurdle for any intraday hypothesis here is **0.30% gross per trade**,
   stated before it is coded. "A high win rate" is this idea again.
2. Reversion's upside is capped by construction, so its mean is bounded near
   the toll. **Breakout and volatility-expansion rules at the same resolution
   have an uncapped tail**, and the package can express them today — this is
   the most promising untested direction (H-INTRA-002).
3. Maker-only execution would change the arithmetic outright and cannot be
   tested without a backtester change, which is its own PR and its own
   argument.
