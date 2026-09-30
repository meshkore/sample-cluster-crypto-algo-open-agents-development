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
