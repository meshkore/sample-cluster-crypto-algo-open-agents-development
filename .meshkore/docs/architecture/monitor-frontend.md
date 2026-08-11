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
  "at": "...", "owner": "blackmac-quantlab-loop", "iteration": 87,
  "stage": "backtest",
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

**`owner` is load-bearing.** It is the handle the work belongs to, and it must
be the same handle the runs that heartbeat launches are submitted under
(`submitted_by`). That identity is the whole basis of the one-card rule below.
A heartbeat without it cannot attribute anything, so the page absorbs every
run in flight into it — correct while one machine is the only worker, wrong the
moment a second one connects.

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

## One card per job, and the centre is only backtests

The rail has three groups and each has exactly one kind of box.

**Running now — one card per JOB, never one per artefact.** A job is one person
or agent doing one piece of work. For our loop that is an iteration, and an
iteration is the whole of it: framing, consulting the cluster, breeding rules,
hundreds of backtests, and finally the single 2026 shot. For a contributor
running from their own machine it is whatever they launched. Two boxes must
mean two workers, never one worker seen from two angles.

That is why the card is titled by **who**, not by what. It used to be titled by
artefact, so the moment the loop opened the sealed window the run it launched
drew a second card and one job read as `loop-087-bear-2026` plus `Iteration 87`
with nothing saying they were the same work.

Attribution is `run.submitted_by === beat.owner`. Runs a heartbeat claims are
its own; whatever is left over is somebody else's job and gets its own card in
the same shape. If you add a new kind of worker, publish a heartbeat with an
`owner` and submit its runs under that same handle, and it will appear
correctly with no page change at all.

**History — one card per HYPOTHESIS, not per run.** Each card already shows both
halves, so listing the training run and the 2026 run separately printed the same
two figures twice under two names. The hypothesis takes the position of its
newest run and opens its 2026 half.

**The centre pane is for backtests and nothing else.** It shows one run: its
figures, its equity curve, its orders, trades, decisions and parameters.
Selecting a job resolves to a backtest — the run in flight, else the last one
that job produced, else its owner's most recent archived run — and a job with
none says so rather than filling the pane with something that is not a backtest.

There is deliberately **no iteration registry** anywhere: no table of recent
iterations, no verdict log, no per-iteration dashboard. What is happening lives
in the left rail and nowhere else. The loop's mechanics are explained once, on
`/loop`, which is a static page and not a record.

## The live page (`/live`) and the journal

`monitor/public/live.html` draws the loop as ten boxes on a **rectangle**, lit as
the orchestrator walks them. It is reached from the small door in the thin bar at
the top of the monitor. The circuit starts **up-left** and turns clockwise —
right along the top, down the right side, left along the bottom, up the left side
— because the path itself is the claim: this ends where it started and goes
again.

A rectangle rather than a ring. A circle puts every box on a tangent, which
forced the type down to 9.5px to fit a shape that was carrying no meaning: the
cycle is the arrows, not the outline. Straight runs give every box the same
width, let the type sit at one size, and leave the middle free for the
hypothesis being tried. **Nothing on this page renders below 12px** — the
diagram scales to about 0.9 on a 16-inch laptop, so its own units are never
below 14.

Ten boxes, not the doc's seven phases. The seven are the phases of a hypothesis;
these are the places the loop can *be*, and three of them were hidden inside one
box. Running a backtest, scoring a finished generation, and putting the result up
against the gate are different things — and the loop turns back between the first
two hundreds of times an hour.

    FRAME → CONSULT → COMPOSE → SEARCH → EVALUATE → DECIDE
          → TRAIN → FORWARD → OBSERVE → RECORD → FRAME

`ResearchLoop.NODE_ORDER` is the same ten, so the drawing and the code cannot
drift.

### The two arrows that go backwards

Most of what this loop does is not forward, and a diagram that only drew the
happy path said otherwise.

- **`breed`** — EVALUATE back to SEARCH. A generation is scored, the survivors
  breed, and every candidate runs again. It fires hundreds of times per
  hypothesis and it is the answer to *does this thing adjust its values, or fire
  one hypothesis and stop*. Lit on the `fit` stage.
- **`refuted`** — DECIDE across to RECORD, skipping TRAIN, FORWARD and OBSERVE
  entirely. A fit that does not clear its module's best never earns a 2026 run,
  so the sealed window is not opened at all. Lit when an iteration is recorded
  without FORWARD having been reached.

Both light exactly as the forward legs do, so the reader can see *where the loop
is* and *which way it just moved*.

**Stages map to boxes in Python, not in the page.** `ResearchLoop.STAGE_NODES`
decides which box a stage lights, and `_emit` stamps `node` and `say` on every
event. A stage added without an entry there lights nothing — which is why the
map lives next to the emits rather than in the HTML. `observed` exists because
OBSERVE was a phase in the architecture doc and an emit nowhere, so the box that
says which module earned the 2026 number had nothing to put in it.

**COMPOSE is not "write the code".** This loop cannot write code. It composes
expression trees over the 79 served columns — data the grammar validates before
anything runs them — and that distinction is the guarantee which makes an
unattended loop safe to leave running. Do not relabel that box.

### The journal

Every event of one hypothesis, in order, appended to
`orchestrator-manager/loop/journal/<id>.jsonl` and kept. The ledger records what
an iteration **concluded** — one line, a verdict. The journal records what it
**did**: each stage, each generation, each advisor reply and refusal, each
backtest. A ledger line cannot answer *is this loop exploring, or circling the
same idea it tried nine iterations ago* — and that question is why this exists.

Deliberately unbounded. An iteration is an hour of work and its record is
kilobytes.

    GET /api/journal          the hypothesis in flight
    GET /api/journal/<id>     one hypothesis
    GET /api/journals         every hypothesis with a journal, newest first

### Two transports, one contract

    local daemon   WebSocket at /ws   — tails the journal file, pushes each line
    public mirror  polling /api/journal every 2s

The page asks which it is in — `GET /health` returns `{"websocket": true|false}`
— rather than opening a socket and discovering the answer from a failed
handshake in every visitor's console. The daemon says `true`; the Worker says
`false`, because nothing on the internet may open a connection back to the
laboratory, and that is a property of the architecture rather than a gap in it.

**The socket tails a file; the loop does not talk to the monitor.** So the
observer cannot slow the research, cannot lose an event to a dropped connection,
and replays the whole hypothesis to a browser that arrives halfway through. A
loop holding a socket open to a monitor makes the observed wait on the observer.

Publishing to the edge is throttled: always on a box change, always at the end of
an iteration, otherwise at most every twenty seconds. A fit emits an event every
few seconds for most of an hour, and a public reader needs to not miss a *stage*,
not to see every counter tick.

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
- **One box per worker in "Running now", one box per hypothesis in the archive.**
  Two boxes mean two people are working, and nothing else may make a second box
  appear.
- **The centre pane never becomes a dashboard.** No iteration table, no verdict
  registry, no loop internals. If it is not one backtest, it does not go there.

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
