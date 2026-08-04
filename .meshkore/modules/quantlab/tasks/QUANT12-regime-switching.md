---
id: QUANT12
title: "Evolve the flagship into a two-part bull/bear regime-switching strategy"
status: completed
priority: high
owner: unassigned
category: quantlab
initiative: liquid-ml-research
created: 2026-08-04
updated: 2026-08-04
tags: [hypothesis, regime, trend, mean-reversion, money-management]
depends_on: [QUANT11]
blocks: []
---

## Why this exists

Direct operator feedback on H-MULTI-001 (QUANT11): a single blended vote
applied uniformly across bull and bear markets is the wrong shape. The
operator specifically asked for a strategy split into two parts, one that
identifies and trades the major bull trend and one for bear markets, with
money management applied on top. This is that evolution, not a new,
disconnected idea — H-MULTI-001 is left as its own recorded result to
compare against, not replaced.

## What was built

`H-REGIME-001`, family `regime_switching`:

- **Regime call**: the classic 200-bar SMA filter (bull if close is above a
  rising 200-bar SMA, bear otherwise) — the most standard, least exotic
  regime indicator in technical analysis, chosen deliberately over
  anything more elaborate for a first pass.
- **Bull branch**: full-confidence (1.0) long on short-term trend +
  momentum agreement, held until both turn against it.
- **Bear branch**: reduced-confidence (0.5) long only on an RSI oversold
  reading — a bounce trade, not a trend trade — closed once RSI recovers to
  neutral. The lower confidence is this hypothesis's money-management
  layer: bet less on a bounce than on a confirmed trend, expressed through
  the same signal-scales-position-size mechanism every strategy here
  already uses, not a new sizing mechanism.
- **Regime override**: a position closes immediately if the regime itself
  flips, regardless of which branch opened it — a bull trend position does
  not ride into a confirmed bear regime, and a bear bounce does not linger
  once the regime turns bullish again.

6 tests, covering both branches, the regime-override behavior, and the
bounce's own exit condition.

## Where this explicitly does NOT overreach

The operator's ask included "a very significant profit, not 3% over 8
months." That specific outcome cannot be manufactured honestly. A backtest
number can be made arbitrarily large by curve-fitting, overfitting to the
tested window, or ignoring costs — and this lab's entire architecture
(Phase-1 sweep + walk-forward + benchmark comparison + a hard drawdown
abort) exists specifically to catch exactly that. This hypothesis is a
genuine, disciplined attempt at what was actually asked for structurally
(two regime-conditional rules, explicit money management by confidence),
not a promise about the number it produces.

## Acceptance criteria

- No exemption from the drawdown limit, cost model, or benchmark
  comparison.
- Compared explicitly against H-MULTI-001 (QUANT11) and against H-REV-001
  (the bear branch's own mechanism, tested standalone) once evidence
  exists for all three.
- Reported honestly regardless of outcome.

## Result (2026-08-04)

S00845, Phase-1 pre-2026 daily/386-asset universe, defaults
(`regime_period=200, trend_period=20, rsi_period=14, oversold_rsi=30,
bull_confidence=1.0, bear_confidence=0.5`): **-8.46% return, 23.97% max
drawdown, 332 trades** (122 wins / 210 losses, 36.7% win rate), 8 assets
traded. `phase1_score` -0.324. Not aborted, but the drawdown came within
1.03 points of the 25% limit that would have aborted it.

The two-part structure did not work in its simplest 200-SMA form. Reported as
run, with the default parameters, rather than swept until some corner of the
grid produced a positive number — the acceptance criteria above committed to
that in advance and the drawdown is the reason it matters: a strategy that
nearly trips the abort is not a tuning candidate, it is a rejected mechanism.

Worth noting against the hypothesis's own recorded invalidator: the bear
branch *is* the H-REV-001 exhaustion-reversal mechanism, which had already
failed standalone. Wrapping it in a regime filter did not fix it, exactly as
that invalidator predicted. Only 8 assets were traded out of 386, so the
regime gate was also far more restrictive than intended.

Not promoted.
