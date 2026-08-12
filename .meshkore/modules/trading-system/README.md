---
title: "Trading system"
category: modules
updated: 2026-08-11
owner: capitaharlock
status: draft
---

# Trading system

**Purpose:** Where a strategy lives — the decisions, and nothing about how they
are measured. Since TRADE1 (2026-08-12) the folder holds **two independent
systems**, and `trading-system/README.md` in the repository is the map.

## Surface

`quantlab_trading/` — **System Four**, on daily bars: regime detection
(`regime.py`, `regime_system.py`), the rule grammar the search mutates
(`grammar.py`, `space.py`), the four-module router, position and risk policy
(`policy.py`), the brain registry (`brains.py`) and the tick contract
(`runner.py`). The last three are the *contract* every system shares.

`quantlab_intraday/` — **the intraday system**, on 5-minute bars: the
microstructure vocabulary and its cost hurdle, the volatility veto, the
reversion brain (H-INTRA-001, the worked example), intraday money management,
the block sampler, the signal study, `prepare` for data and cached indicator
panels, and the paired launcher. Read its `README.md` before proposing an
intraday rule: it states the 0.30%-per-trade hurdle any such rule has to clear,
and the measurement that established it.

The separation is enforced, not conventional:
`orchestrator-manager/scripts/check_layering.py` fails the build if either
system imports the other's decisions, or if either imports the manager.

## Where a contribution lands

Here, and registering is still the only wiring step. Which package depends on
the horizon: a major-trend rule, a regime branch or daily money management goes
to `quantlab_trading/`; a mechanism measured in hours on bars measured in
minutes goes to `quantlab_intraday/`. See `.meshkore/public/BACKTESTING.md` for
how to run one and what result to report.
