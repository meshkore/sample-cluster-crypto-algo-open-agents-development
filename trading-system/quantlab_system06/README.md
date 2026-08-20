# Generation six — the oracle-taught net (15m)

**A new research line, not another branch of the ITSM lineage.** The
`system04`/`system05` folders chase one champion (the 06:00 momentum entry) by
adding discretion to it. This folder asks a different question, so it is its own
system beside `quantlab_trading` and `quantlab_intraday` and it depends on the
**contract only** — `Decision`, `@register`, `MoneyManagement` — never on another
system's decisions. `orchestrator-manager/scripts/check_layering.py` enforces that.

## The hypothesis

Buy-and-hold from 10 to 30 is +200%. A trader who caught a hundred clean 10%
swings on the way — buying each dip, selling each rip — compounded far more than
+200% on the same tape. The ceiling of a chart is therefore **not** its start-to-end
move; it is the sum of every swing a long-only trader could have captured. That
ceiling is computable with perfect hindsight, and it is enormous.

So the plan is behaviour cloning of a perfect-hindsight trader:

1. **The oracle (`oracle.py`).** A dynamic program looks at the *whole* chart with
   full future knowledge and marks the long-only trade set that maximises the
   compounded return, subject to a minimum per-swing move (start: **1% gross**).
   Its output is one bit per bar: *should a perfect trader be holding here, or
   flat?* That is the teacher.
2. **The features (`features.py`).** For every bar, a **causal** description: a
   window of the last K candles (normalised) plus a curated subset of the ~79
   indicators the instrument already computes. Normalised on **training
   statistics only** — no bar ever sees a number derived from its own future.
3. **The net (`model.py`, `train.py`).** A compact neural network learns to
   reproduce the oracle's bit from the causal features alone. Trained on GPU with
   mixed precision; validated with a purged, embargoed walk-forward so an
   observation is never scored by a model that saw its neighbours.
4. **The bridge (`infer.py`, `strategy.py`).** The trained model is *exported*,
   its per-bar signal is precomputed to a table (the `system05` pattern — a brain
   that recomputes features live is a second implementation that silently drifts),
   and a thin brain reads that table and emits `Decision`s. Orders fill at the
   **next** open; the no-lookahead line the instrument enforces is never crossed.

## What "different" has to mean here

The oracle sees the future — that is the point, and it is only ever the *training
target*, never a feature. The test of the whole idea is the gap between the
teacher and the student: the oracle's compounded return is the unreachable
ceiling, and what matters is how much of it a net that sees only the past can
keep, first on the research era and then on the sealed 2026 window it was never
fitted on.

## Scope, deliberately minimal for v1

- One symbol: **BTCUSDT**. One timeframe: **15m**.
- One label: the oracle's in/out bit at a 1% gross swing threshold.
- One model, exported once, replayed without the trainer.

More symbols, more timeframes and a cost-aware threshold are the obvious next
steps and are left out on purpose until the end-to-end path measures something.

## Running it

```bash
python3 -m quantlab_system06.dataset --download      # BTCUSDT 15m: research + forward
python3 -m quantlab_system06.oracle  --plot          # the teacher, and its ceiling
python3 -m quantlab_system06.train                   # GPU train + purged walk-forward
python3 -m quantlab_system06.infer                   # export signal table
# then the brain `system06-oracle-net` is launchable through the harness
```

## The number to beat

The incumbent sealed 2026 result is **+5.05%** (`intraday-itsm-30d`), and
buy-and-hold was **−35.58%** that year. This system is a workshop until an
attempt clears +5.05% on the sealed window inside the 25% drawdown mandate.
