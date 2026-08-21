# system 06 decision modules

Each module is one small, independent judge. The orchestrator
(`../orchestrator.py`) assembles the bar once, polls every module, and combines
their opinions into a single long-only portfolio decision. The module never
touches the account, never computes a fill, and never stops the run — those belong
to the orchestrator and the 25 % mandate.

## The contract (`base.py`)

```
MarketView   timestamp, ns, candles, account, channels, held, peaks   (assembled once/bar)
SymbolVote   conviction 0..1 · veto · size_mult · exit_now/exit_reason (per symbol)
ModuleOutput votes{symbol:SymbolVote} · deploy · deploy_mult · note
Module       name · weight · evaluate(view)->ModuleOutput · reset()
```

How the orchestrator folds the votes, each bar:

- **direction** — a weight-weighted mean of the *directional* votes (conviction > 0).
  A name enters only if that score clears `enter`, no module vetoes it, and at least
  `consensus_k` modules back it. Non-directional modules (weight 0) never dilute the mean.
- **exits** — a module may `demand_exit` a held name; the highest-priority demand
  (STOP > RISKOFF) fires immediately, ignoring `min_hold`. Otherwise a conviction exit
  fires once the score falls to `exit_` past `min_hold`.
- **deploy** — `deploy` suggestions (regime) are reconciled to the most defensive, then
  scaled by the product of `deploy_mult`s (money management), clamped to [0.05, 1.0].
- **size** — `equity · deploy / max_positions`, times the product of the per-symbol
  `size_mult`s (vol targeting, Kelly, microstructure).

## The modules

| module | job | lever(s) | off when |
|---|---|---|---|
| `oracle_nn` | the TCN's per-bar conviction (the primary) | — | never (always on) |
| `meta` | refuse entries the secondary model expects to lose | `meta_margin` | `None` |
| `stops` | hard + trailing stop exits | `stop_loss`, `trail_stop` | both ≤ 0 |
| `regime` | breadth risk-off + dynamic deployment | `breadth_gate`, `regime_deploy`, `regime_persist` | all ≤ 0 |
| `volatility` | vol-target position sizing | `vol_scale`, `vol_floor` | `vol_scale` ≤ 0 |
| `momentum` | cross-sectional relative-strength gate | `mom_gate` | ≤ 0 |
| `money` | fractional-Kelly sizing + anti-martingale deploy | `money_kelly`, `money_pyramid` | both 0 |
| `microstructure` | contrarian veto from funding/OI/liquidations | `micro_gate` | `None` / no data |

Every module self-disables when its lever is off, so the module list is stable and the
ensemble with all levers off is byte-identical to the retired monolith (pinned by
`tests/test_ensemble.py` against a golden fixture).

## Channels

Heavy work is precomputed *offline* into causal per-(symbol, bar) channels and looked up
in microseconds at decide-time — the pattern that keeps backtest and future real-time fast:

- `signals.npz` — `prob`, `trend`, `vol`, `mom` (built by `infer.py`).
- `meta.npz` — `meta` expected-net verdicts (built by `meta.py`, honest walk-forward).
- `micro.npz` — `micro` contrarian score (built by `microstructure.py`, pending a data feed).

`channels.py` is the single loader; no module re-implements a lookup.

## Adding a module

1. Write `modules/<name>.py` with a class exposing `name`, `weight`, `evaluate(view)`,
   `reset()`. Read only from `view`; return a `ModuleOutput`. Self-disable when your lever is off.
2. If it needs precomputed data, add a causal channel + a `channels.py` accessor + an
   offline builder — never compute heavy state inside `evaluate`.
3. Add it to `build_ensemble` with an off-by-default lever, and expose that lever on the
   `OracleNetBrain` adapter (and its `parameters()` only when active, so fingerprints are stable).
4. Add a unit test, and confirm `tests/test_ensemble.py` golden is unchanged when the lever is off.
5. The autoloop can then explore it on validation via a named dict row in `risk_grid.json`
   — **never** selected on 2026.

Run `python -m quantlab_system06.modules` to list the modules and their levers.
