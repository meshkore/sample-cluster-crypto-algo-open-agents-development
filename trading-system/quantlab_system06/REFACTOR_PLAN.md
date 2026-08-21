# System 06 → modular ensemble: architecture & plan

**Goal.** Turn the monolithic `OracleNetBrain.decide()` — where every idea lives
as an inline flag (`stop_loss`, `vol_scale`, `mom_gate`, `breadth_gate`,
`regime_deploy`, `regime_persist`, …) — into a set of **independent, testable
decision modules** combined by one **orchestrator**, so we can add the levers the
research proposed (meta-labelling, real money-management, microstructure
sentiment, consensus voting) without the file turning into a swamp, and so the
same orchestrator can eventually read the market live and combine module verdicts
**in parallel, fast**.

This is an **evolution of system 06**, not a new system. The monitor keeps seeing
the `system06-oracle-net` family; the NN becomes one module among several.

## Design principles (non-negotiable)

1. **Precompute heavy, combine cheap.** Model inference, walk-forward meta
   verdicts and any exchange-data fetch are computed *offline* into causal
   channels (the `signals.npz` pattern already in `infer.py`). At decide-time
   every module does O(symbols) lookups + arithmetic — microseconds per bar.
   Speed for backtest *and* future real-time comes from this, not from threads.
2. **One channel store, one loader.** All the scattered `self.table.get(sym,{})…`
   lookups collapse into a single `channels.py` helper. No second implementation
   of the same arithmetic (the bug `quantlab_ml/meta.py` warns about).
3. **Modules are independent.** Each lives in `modules/<name>.py`, has a single
   job, holds only its own state, resets per run, and is runnable standalone
   (`python -m quantlab_system06.modules.<name> --explain`). Disable a module →
   it abstains → orchestrator behaves as if it were never there.
4. **Money management is the outer layer, always on.** Direction is decided by a
   weighted, consensus vote of the directional modules; *size* is then decided by
   the money module (deploy fraction × fractional-Kelly × vol-target ×
   anti-martingale pyramiding), bounded by the 25 % peak-to-trough mandate.
5. **Honesty rules unchanged.** Long-only, research-only. Selection uses
   validation (pre-2026) only. **2026 is sealed forward, never feedback.** Every
   new channel is causal and, where it is learned (meta), uses purged
   walk-forward with the final model alone scoring 2026.

## Scope of "clean up the junk"

**Important:** `quantlab_intraday`, `quantlab_ml`, `quantlab_system04/05` and
`quantlab_trading` are **not dead** — `orchestrator-manager/` (the Mac effort)
and the backtester/contract tests import them. Deleting them would break the
wider cluster. **Cleanup is scoped to `quantlab_system06` + `research/system06`**:
the monolith, duplicated lookups, and stale artifacts (`signals_v2.npz`,
`signals_gated.npz`, `__pycache__`, `*.out/*.err`, `_pre_consistency` ledger).
`quantlab_ml`'s honest walk-forward machinery is *reused*, not duplicated.

## Module contract (`modules/base.py`)

```
MarketView   : timestamp, ns, candles, account, channels, held   (assembled once/bar)
SymbolVote   : conviction 0..1, veto: bool, size_mult: float      (per symbol)
ModuleOutput : votes {symbol: SymbolVote}, deploy: float|None, note
Module       : name, weight; evaluate(view) -> ModuleOutput; reset()
```

Orchestrator combines each bar:
- **direction**: weighted mean of `conviction` over modules; a symbol enters iff
  score ≥ `enter` **and** no module vetoes **and** ≥ `consensus_k` modules agree.
- **book deploy fraction**: the money module reconciles the regime/money `deploy`
  suggestions into one fraction (defensive floor → bull cap).
- **per-symbol size**: `deploy/slots × ∏ size_mult` (vol-target, microstructure),
  bounded.
- **exits**: stops/risk-off/conviction-gone, in that priority (as today).

## Phased execution (each phase ends green: full test pass)

- **Phase 0 — scaffolding** ✅ `modules/base.py` (contract), `channels.py` (single
  loader over `signals.npz`, pure numpy), `orchestrator.py` (`EnsembleBrain`),
  `modules/oracle_nn.py`. Additive, nothing removed.
- **Phase 1 — port the inline features to modules** ✅ `stops`, `regime` (breadth
  risk-off + `regime_deploy/persist`), `volatility`, `momentum`. **Monolith retired**
  to a thin adapter; equivalence proven scripted (9 configs) + real-data 2023, frozen
  by `tests/fixtures/ensemble_golden.json`. `launch.py`/`autoloop.py` unchanged.
- **Phase 2 — meta-labelling** ✅ `meta.py` builds an honest, expanding, time-purged
  walk-forward verdict channel over system 06's own candidate entries (final research
  model alone scores sealed 2026); `modules/meta.py` vetoes negative-edge entries.
  Real build: 800,922 candidates, ~7 % positive expected-net.
- **Phase 3 — money management** ✅ `modules/money.py`: fractional-Kelly per-name
  sizing from the meta edge + bounded anti-martingale deploy (presses winners, never
  martingales into losses). Off by default.
- **Phase 4 — microstructure sentiment** ✅ (scaffolded) `microstructure.py` scoring
  (funding / OI / long-short liquidations → causal contrarian score) + `modules/
  microstructure.py` veto. **Read-only, no derivatives trading.** Ships off, pending a
  derivatives-data feed the local `backtester/data` doesn't yet carry.
- **Phase 5 — consensus & selection** ✅ `consensus_k` (K-of-N) lever; the autoloop now
  accepts **named dict rows** in `risk_grid.json` so meta/money/micro/consensus are
  explorable **on validation only** (never 2026); card/sweep surface active levers.
- **Phase 6 — cleanup & docs** ✅ Monolith removed, lookups centralised, `modules/
  README.md`, `python -m quantlab_system06.modules` introspection. (`quantlab_intraday/
  ml/system04/05` are NOT removed — the Mac orchestrator imports them.)

## Status: all phases landed. Off-by-default so the live champion is untouched until each
new lever is selected on validation. Next: run the meta/money A/Bs through the autoloop,
keep what lifts consistency, drop what doesn't; wire a derivatives feed for microstructure.

## Real-time forward (why this shape is fast live)

At 15 m bars, decide-time is µs because channels are precomputed. The only
modules that need a live network call in real time are the I/O ones (microstructure
funding/OI). The contract keeps `evaluate` sync + cheap; the orchestrator exposes
a `gather` seam so those I/O modules can be fetched concurrently (thread pool /
async) without changing any module. Offline channel building fans out across
processes. No module blocks another.
