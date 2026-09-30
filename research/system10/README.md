# research/system10 — the conditioned policy's working area

Belongs to `trading-system/systems/system010_conditioned_rl/`. **The system is the package;
this folder is where its runs happen.** The plan both of them execute is
`.meshkore/context/system10-design.md`.

| path | what it holds |
|---|---|
| `DESIGN_DOSSIER.md` | S10-3: every default of the design argued against the published record, with citations |
| `DATA_AUDIT.md` | S10-4: gaps, duplicates, clock alignment, publication lags, and the proof that the 2026 seal holds |
| `knowledge/sources.jsonl` | one line per source read, in the same shape as system 06's |
| `rnd/agenda.jsonl` | the ideas, each closed with a measured result and never deleted |
| `rnd/program.jsonl` | the queued experiments the runner executes |
| `rnd/program_progress.jsonl` | the per-arm tape: one line the moment an arm is scored |
| `rnd/conditions_<date>.json` | S10-6: the region, its rules, and its coverage per year |
| `tools/` | one-off measurements; each writes a dated JSON beside itself |
| `autotest.py` | the paired-experiment runner (S10-9), a 010 copy of 06's |
| `model_card.json` | what the dashboard's Training tab shows instead of a curve |
| `STOP_S10` | the brake: while this file exists the watchdog leaves 010's training stopped |

## `model_card.json` — the training side the dashboard shows

010 is an `ai-model` system (declared in its `docs/context.json`), so its training side on
the dashboard is a **model card**, not a curve. The trainer writes this file; nothing else
does. Until it exists the systems list shows *"Model card not published yet"* in 010's
Results tab — never a blank and never a zero.

How it travels: `mock_server._systems()` reads `research/<id>/model_card.json` for every
system whose context declares `system_type: "ai-model"` and attaches it as `model_card`
(`null` when absent). `cf_pusher.build_systems()` is that same function, and its output rides
the details map under the reserved id `__systems__`, which the deployed Worker already
serves — so a new or changed card reaches the public page **with no deploy**. The
orchestrator monitor reads the same path through `monitor_server._model_card()` (family
token `system10`).

The continuous trainer (`continuous.py`) also appends one row per 5-hour reading to
`rnd/forward_log.jsonl`; `_system_model_card()` adds the **last** row's `forward_equity` per
lineage to the card as `latest_forward_equity` (whole dollars, the log itself never travels).
The Results tab draws, from `forward_history`, 2026 return and 2026 max drawdown vs training
hours per lineage (naive-region baseline as a dashed reference), the latest 2026 equity, a
stats row and the frozen region rules. Test fixture: `research/system06/preview/fixtures/system10/`.

Every field is optional; the page renders a dash for anything missing. Fractions are
fractions (0.83, not 83). Years are string keys.

```jsonc
{
  "system": "system10",
  "family": "system10-conditioned-rl",
  "system_type": "ai-model",
  "status": "region | cloning | offline-rl | ppo | exported | stopped",
  "updated_at": "2026-10-04T12:00:00+00:00",

  // the walk-forward fold in progress: trained on years <= trained_through, judged on current_year
  "walk_forward": {"current_year": 2024, "trained_through": 2023,
                   "validation_years": [2024, 2025]},

  // S10-6: the region R, and how much of the best trades / of the tape it covers, per year
  "region": {"version": "r0-gates", "target_coverage": 0.80,
             "coverage": {"2018": {"best_trades": 0.83, "bars": 0.21}}},

  // S10-7: behaviour cloning of system 06 - the baseline, scored on VALIDATION years only
  "clone": {"status": "done",
            "validation": {"2024": {"return": 0.12, "max_drawdown": 0.08, "q": 0.18, "trades": 140}}},

  // S10-8: offline RL (CQL / IQL); beats_clone is null until both validation years are read
  "offline_rl": {"algorithm": "IQL", "status": "running", "beats_clone": null,
                 "validation": {"2024": {"return": 0.15, "max_drawdown": 0.07, "q": 0.32, "trades": 118}}},

  // four seeds per configuration; the spread is reported, never the mean alone
  "seeds": {"planned": 4, "done": [0, 1], "spread": {"q": 0.21, "return": 0.05}},

  // the one heavy GPU lane (RTX 4060): free | held | queued | braked
  "gpu_lane": {"state": "held", "holder": "system10 offline-rl",
               "since": "2026-10-04T09:00:00+00:00",
               "brake": "research/system06/STOP_AUTOLOOP"}
}
```

No 2026 figure ever goes in this card: the sealed reading is recorded in the package's
`docs/RESULTS.md` and `context.json`, once.

## What is committed here and what is not

Committed: the record — the dossier, the audit, the agenda, the programme, the progress tape,
the conditions files, the tools that produced a number, and the model card.

Not committed, regenerated on demand: `*.npz`, `*.pt`, `*.log`, `*.err`, `*.out`, `_auto_*`,
`__pycache__`. If a run leaves a log behind, it is scratch — delete it rather than commit it.

## Two rules that are not conventions

- **No 2026 bar is loaded here** except by S10-11's sealed reading. Research ends at
  2025-12-31 and a sealed reading is spent, never repeated.
- **Nothing in this folder writes into `research/system06/`.** 010 reads 06's package as a
  declared lineage; the champion's working area is not shared.

## Data does not live here

Every candle, indicator panel and external series is under `trading-system/backtester/data/`,
reached through `quantlab_catalog`.
