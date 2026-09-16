# research/ — the runtime workspace

**Nothing in here is a trading system.** The systems are packages under
`trading-system/systems/`; this folder is where their *runs* happen — scratch signals,
sweep results, loop state, agent notes and the local preview servers.

| folder | belongs to | what it holds |
|---|---|---|
| `system06/` | `trading-system/systems/system006_oracle_net_15m/` | the champion's working area: signal arrays, the R&D diary and agenda, the architecture registry (`registry/ARCH-000N`), the knowledge base, `tools/` for one-off experiments, and `preview/` — the local dashboard and the Cloudflare pusher |
| `system08/` | `trading-system/systems/system008_residual_momentum_ls/` | the closed system's experiments, iterations and `POSTMORTEM.md` |
| `system09/` | `trading-system/systems/system009_participant_ledger/` | the stopped system's phase reports and its local viewer |
| `agent_runs/` | shared | per-agent scratch output. Gitignored. |
| `quantlab.db` | the lab | the orchestrator's runtime database. Gitignored. |

The folder names carry the system NUMBER, which is the identifier that never changes. The
package folders carry the number *and* a description of the hypothesis, because that is
what a reader needs when they are looking at nine of them at once.

## What is committed here and what is not

Committed: the record — diaries, agendas, registries, reports, the tools that produced a
number, and anything a later reader would need to understand a decision.

Not committed, and regenerated on demand: `*.npz` signal arrays, model weights, `*.log`,
`*.err`, `*.out`, `__pycache__`, the database. `.gitignore` carries the list. If a run
leaves a log behind, it is scratch — delete it rather than commit it.

## Data does not live here

Every candle, indicator panel and external series is under
`trading-system/backtester/data/`, reached through `quantlab_catalog`. There used to be a
second store at `backtester/data/`; it held 14 GB of leaked per-run copies and was deleted
on 2026-09-16. If a path in a script points at it, that script is stale.
