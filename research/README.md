# research/ — the runtime workspace

Since System 11 (2026-10-19), a system's CODE and runs live here (`research/plan_v2/`, `research/system12/`),
while its RECORD (SUMMARY / RESULTS / context.json, shown in the Strategies tab) lives in
`trading-system/systems/systemNNN_*/docs/`. Older systems keep their code under `trading-system/systems/`.

| folder | status | what it holds |
|---|---|---|
| `system12/` | **ACTIVE** | System 12, the only running system: paper book, the search that defined it, the page documents. **Start at its README.** |
| `plan_v2/` | archived (System 11) | System 11 and its experiments; still imported by System 12 (`history_v2`, `classics11`, `bayes11`, `rocket11` cache) - do not move. See `ARCHIVED.md`. |
| `architecture_brief/` | live page | the public review-request page (now round 4, System 12) and its deploy script |
| `system06/` | infrastructure | `preview/` holds the Live dashboard (`dashboard.html`), `mock_server.py` (its data) and `cf_pusher.py` (pushes it to Cloudflare); the rest is System 06's archive |
| `system10/` | archived | System 10's working area; `tools/` is still on the PYTHONPATH (point-in-time lists); `RESTART_pusher` is the flag that restarts the pusher |
| `rocket/` | archived | the System 10 validator search (stopped, `STOP`) |
| `system08/`, `system09/` | archived | closed systems, kept as record |
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
