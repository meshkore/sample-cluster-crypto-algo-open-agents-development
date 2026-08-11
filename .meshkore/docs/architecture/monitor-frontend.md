---
title: "The monitor frontend and its data contract"
category: architecture
updated: 2026-08-11
owner: master
status: active
---

# The monitor frontend and its data contract

Read this before changing the page, before adding a field the page should show,
and before launching a backtest you expect to appear on it correctly. Most of
what has gone wrong on this surface was not a rendering bug — it was data
arriving in a shape the page could not interpret, and the page guessing.

## The three copies of the page

There is no build step, no framework, no bundler and no package.json. The page
is one self-contained HTML file with inline CSS and JS. It exists in three
places and **only the first is editable**:

| path | what it is |
|---|---|
| `monitor/public/index.html` | **the source of truth.** Edit this one. Also `loop.html`. |
| `orchestrator-manager/cloudflare/public-mirror/public/index.html` | generated copy for the Worker. Never hand-edit — `sync-ui.sh` overwrites it. |
| `~/Library/Application Support/QuantLab/monitor/public/index.html` | the runtime copy the local daemon actually serves. A hand copy. |

The local daemon reads its copy from disk on **every request**, so replacing
that file is enough — no restart. The Worker needs a deploy.

```bash
# after editing monitor/public/index.html
cd orchestrator-manager/cloudflare/public-mirror
sh sync-ui.sh          # copies BOTH pages into the Worker's assets
node test.mjs          # 29 tests over the Worker's API contract
npx wrangler deploy
cp ../../../monitor/public/index.html \
   "$HOME/Library/Application Support/QuantLab/monitor/public/index.html"
```

Skipping `sync-ui.sh` is the classic failure: the page you tested locally is not
the page the public sees, and nothing warns you. Skipping the runtime copy is
the other half: you deploy publicly and the operator's own monitor is unchanged.

The page makes **no external requests** — no CDN, no fonts, no analytics. Keep
it that way; the Worker serves it under an asset policy that would break them,
and an offline-capable single file is why the local and public monitors can be
literally the same bytes.

## What the page reads

Three endpoints, identical in shape from the local daemon
(`quantlab_manager/monitor_server.py`) and from the Worker
(`cloudflare/public-mirror/src/index.js`). **One shape, two hosts** — if you
change one you must change the other, or the public page silently diverges.

| endpoint | returns |
|---|---|
| `GET /api/backtests` | `{best_2026, live[], history[]}` — the left rail |
| `GET /api/backtests/<id>` | `{run, equity[], orders[], trades[], decisions[], regimes[]}` — the detail pane |
| `GET /api/loop` | the research loop's heartbeat — the "running now" card |

The page polls. There is no SSE and no WebSocket: an earlier version opened an
EventSource on a route the daemon never served, retried it forever, and that is
why "live" showed nothing for weeks. A stream out of this machine could never
work through the public mirror anyway.

## The two-era model — the thing the page is FOR

Every hypothesis in this laboratory has exactly two possible results:

- **training** — what it did over the years it was allowed to be fitted on,
  everything ending on or before `2025-12-31`.
- **2026** — what it did in the sealed forward window, which is never optimised
  against and never fed back.

These are **two separate runs**, not two slices of one run. The page shows both
on every card, labelled, with the 2026 figure larger, because a percentage
without its era is not information — it is a number that could mean either of
two opposite things.

### `era` and `pair_key` are derived, never stored

Both come from `quantlab_manager/backtests.py:describe()`, which decorates a row
on read. That is deliberate: 134 historical rows gained both the moment the
function existed, with no migration.

**Any new code path that returns run rows must call `describe()`.** A row that
reaches the page without `era` falls back to a weaker client-side rule; a row
without `pair_key` can never be paired and its card will say the other half was
never run.

```python
era_of(run)     # "2026" if trade_from >= 2026-01-01 else "training"
pair_key(run)   # sha1(strategy_family + genome-without-trade_from)[:16]
```

`era_of` reads `strategy_params.trade_from` — **the first bar the run was
allowed to TRADE**, never `window_start`. They are different dates and confusing
them has caused every bug in this area: a 2026 forward run loads from 2017 so
the regime detector inherits the whole market cycle, so its `window_start` says
2017 and says nothing about what it measured. Reading `window_start` as the era
is how the public page once crowned a 2022–2025 result as "best in 2026".

### If you launch runs by hand, launch BOTH halves

`pair_key` hashes the strategy family plus the genome with `trade_from` removed.
Two runs are the same hypothesis when they are the same strategy carrying the
same genome, and the **only** parameter allowed to differ is where trading
starts — that is precisely what makes them two halves rather than two copies.

So, for an agent submitting work:

- Submit a training run and a 2026 run with **identical parameters except
  `trade_from`**. Any other differing parameter makes them two unrelated
  hypotheses and both cards will report the other half missing.
- The label does not matter. Pairing used to match `-training` against `-2026`
  suffixes, which worked for the loop's own runs and paired nothing at all for
  every hand-submitted one.
- A hypothesis with only one half is not an error and is not hidden. The card
  states which half is missing and why. But it also cannot be compared with
  anything, which is most of its value.

## Required fields on a run row

For a card to render fully:

| field | why the page needs it |
|---|---|
| `backtest_id` | identity, and the detail route |
| `label` | the card's name |
| `created_at` | the timestamp line, and the newest-wins tiebreak when a genome is re-run |
| `status` | `running` puts it in the live group; anything else is archive |
| `strategy_family` | half of `pair_key`, and the meta line |
| `strategy_params_json` | the other half of `pair_key`, and the source of `trade_from` |
| `return_pct` | the figure itself |
| `trades` | under the figure, and the champion rule below |
| `max_drawdown` | under the figure |

The detail pane additionally uses `final_equity`, `win_rate`,
`average_exposure`, `window_start`, `window_end`, `submitted_by`,
`universe_size`.

`trades = 0` is **not** missing data. It is a complete result meaning the
configuration stood aside for its whole window. It is excluded from the
champion ranking and from nothing else.

## The heartbeat contract

`GET /api/loop` returns what `ResearchLoop._beat()` publishes. The page renders
it as the "running now" card and, when selected, as its own detail view.

```jsonc
{
  "at": "...", "iteration": 87, "stage": "backtest",
  "phase": "running backtests, all of them before 2026",  // PHASE_LABELS[stage]
  "module": "BEAR", "started_at": "...", "symbols": 386,
  "fit":           { "generation": 2, "of": 4, "best": -0.0285, "...": "..." },
  "last_backtest": { "window": {...}, "fold": 1, "folds": 4, "return_pct": 0.0075,
                     "trades": 45, "max_drawdown": 0.0047, "backtests": 45,
                     "planned": 160, "best": -0.0285 },
  "pair":          { "training": {...} | null, "forward": {...} | null },
  "incumbent_forward": 0.0027, "consecutive_failures": 0, "recent": [ ... ]
}
```

Two fields are easy to confuse and mean very different things:

- **`last_backtest`** is one fold of one candidate out of some hundreds. It
  changes every few seconds. It is the arithmetic that produces a result, **not
  a result**, and must never be presented as one.
- **`pair`** is the iteration's two actual results: `training` is the accepted
  genome's run over the years before the lock, `forward` is the single 2026
  shot if the fit cleared its gate. Both are `null` until they happen, and both
  are cleared on the `begin` stage so one iteration's numbers cannot appear
  under the next one's heading.

If you add a stage, add it to `ResearchLoop.PHASE_LABELS` or the card shows the
raw stage slug. Say what is HAPPENING, not what the stage is called — a reader
asked what "fitting" meant and could not tell whether the machine was
downloading data, computing indicators, writing code or running backtests.

A heartbeat older than 20 minutes renders as stale, with the age. The observer
never raises: `_beat` swallows its own failures, because an observer that can
stop the research is worse than no monitor.

## Adding a field, end to end

Six places, in this order. Missing one gives you a field that works locally and
is absent in public, or vice versa.

1. **Produce it** — the backtester writes it to `backtest_runs`, or the loop
   puts it in the heartbeat event.
2. **Read it** — `sessions.py:sidebar()` / `backtests.py:run()` select `*`, so a
   new column arrives automatically. A new *derived* value goes in
   `backtests.py:describe()` so every read path gets it.
3. **Publish it** — the mirror publisher sends `detail.run` verbatim, so a
   column on the row travels. A field the Worker must compute needs adding to
   `src/index.js` too.
4. **Mirror it** — if the Worker derives anything about it, add a case to
   `test.mjs`. The Worker's copy of a rule drifting from the daemon's is exactly
   how the public champion once differed from the local one.
5. **Render it** — `monitor/public/index.html`.
6. **Ship it** — `sync-ui.sh`, `test.mjs`, `wrangler deploy`, runtime copy.

Prefer deriving in `describe()` over storing. Storing means a migration and an
archive split between rows that have the field and rows that do not.

## Rules the page must keep

Each of these was a real defect, not a style preference.

- **Never show a percentage without saying which era it measured.** One number
  per card is what let a +8.42% fit sit above a +0.27% forward test and read as
  a collapse.
- **The archive is a record, never a leaderboard.** `history` is chronological,
  newest first. Ranking it by return would quietly turn the honest sequence of
  attempts — most of which failed — into a highlight reel.
- **A run that never traded cannot be champion.** Standing aside finishes at
  exactly +0.00%, which beats every honest loss and wins every sort. The
  `trades > 0` clause exists in the daemon, the Worker and the page for that
  reason.
- **Missing data says why.** Never render an absent value as `0.00%`, and never
  render an empty panel — say "2026 never opened on it", which is the honest
  answer for a fit that broke its drawdown budget.
- **Twins are resolved when the reader asks, not stamped in when the run
  finished.** A training run published before its 2026 half existed would
  otherwise say "no 2026 half" forever.
- **The equity chart draws the window the run TRADED**, never its run-up. A 2026
  run's pre-2026 bars are a flat line at opening capital by construction.

## Deleting runs

The local SQLite database is the authority; the mirror is a presentation copy.
Deleting locally does **not** remove anything from the public page — the
Worker's R2 index is only ever appended to by `POST /api/backtests/<id>` and has
no delete path. A local deletion must be followed by rewriting
`backtests/index.json` in R2 and deleting the orphaned `backtests/<id>.json`
objects, or the two surfaces disagree and the public page keeps serving runs the
laboratory no longer holds.

The child tables carry no `ON DELETE CASCADE`, so delete
`backtest_equity`/`orders`/`trades`/`decisions` **before** the parent row and
finish with `PRAGMA foreign_key_check`.

Before deleting anything, check `loop/ledger/loop-state.json`: if
`incumbent_backtest_id`, `last_forward_id` or `last_training_id` names a row you
are removing, the running loop will fail at its next `frame()`. Stop it, repair
the state file, then restart.

## Related

- [[docs/deploy/public-state-mirror]] — the Worker, R2 layout, publish token
- [[docs/deploy/public-surfaces]] — what is public and why
- [[docs/ops/infrastructure]] — deploy commands, LaunchAgents, credentials
- [[docs/architecture/research-loop]] — what produces the data on this page
