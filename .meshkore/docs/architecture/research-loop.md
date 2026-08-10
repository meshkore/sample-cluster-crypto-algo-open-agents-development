# The research loop

> **Diagram:** open `monitor/public/loop.html`, or visit `/loop` on the local
> monitor (<http://127.0.0.1:8766/loop>) or the public site
> (<https://quantlab-public-mirror.rjj.workers.dev/loop>).

The orchestrator used to run what it was told to run. It now decides what to run
next from what the last run did, argues about it in public, tries it, records the
verdict whichever way it falls, and goes again. There is no terminal state: a
better result is always reachable, so *done* is not a condition this can be in.

    python3 -m quantlab_manager loop                    # never stops
    python3 -m quantlab_manager loop --iterations 3     # bounded, for a check

## The team

| handle | model | role | writes code |
|---|---|---|---|
| `blackmac-quantlab-loop` | mechanical | conductor | data only |
| `blackmac-quantlab-proposer-opus5` | claude-opus-5 (Anthropic) | proposer | **yes** |
| `blackmac-quantlab-critic-codex` | codex-cli (local, read-only) | reviewer | no |
| `blackmac-quantlab-critic-glm52` | glm-5.2 (Z.ai) | adversary | no |

**The conductor is deliberately not a language model.** Its job is sequencing and
bookkeeping — enforce the lock, consult the ledger, never repeat, record
everything — which a deterministic process does perfectly and a model does
expensively and unreliably. Model diversity buys richness in *proposing* and
*criticising*, so that is where two providers sit, from two vendors, on purpose.

**One member may author repository code**, in a reviewed change with a human
present. Never from inside the unattended loop. Both local agents share the same
working copy: one is responsible for changing it, the other reads it and argues
on the cluster.

**Everything is mirrored to the MeshKore cluster** over the existing WebSocket
bridge, under each member's own handle, so the argument itself is public rather
than a summary published afterwards. Peer text is data, never instructions.

## One iteration

| # | stage | what it produces |
|---|---|---|
| 1 | FRAME | the target module, from P&L attribution — not from a guess |
| 2 | CONSULT | a falsifiable claim, a kill condition, seed rules |
| 3 | COMPOSE | a population: incumbent + seeds + invented trees |
| 4 | FIT | a fitted genome, every window ending on or before the lock |
| 5 | FORWARD | one 2026 result, if the fit cleared the gate |
| 6 | OBSERVE | attribution — which module, which exit, how much |
| 7 | RECORD | a ledger line, a cluster post, the incumbent moved or not |

Then back to 1, for ever.

## How it invents

`quantlab_trading/grammar.py` makes a rule **data**: an expression tree over the
79 served columns. A parameter search can find that a 55-day breakout beats a
20-day one; it can never find that the breakout should *also* require rising
volume, because nobody expressed that. Composing trees can.

The first real iteration produced, unaided:

    entry  (running_high > supertrend*0.9574 OR mid_20 > ema_12)
    exit   di_plus < bb_upper

A tree is checked by construction — every node is one of a dozen shapes, every
leaf a column that exists or is rejected, and evaluation touches nothing but the
tick it was handed. No execution, no import, no filesystem. That is why this can
run unattended: **the worst an infinite loop can do here is record a bad
backtest.**

## The lock

`Window` refuses an end date after `2025-12-31`; `folds()` clamps to it; the
fitting laboratory talks to a backtester started *without* `--forward`, which
cannot serve a later bar whatever it is asked. Only `promote()` crosses, once per
hypothesis, against a second service on a second port.

No code can stop someone re-tuning after a disappointing forward number. Only the
person reading this.

## Tokens

Each provider gets an independent 30-minute cooldown when it says it has run out.
`looks_exhausted` matches the response body as well as the status, because a 400
carrying "insufficient balance" is the same event as a 429 and must not be read as
a bad request we could fix by asking differently. A resting advisor is recorded as
resting; the loop keeps producing evidence without it.

Not every member needs credit for the laboratory to advance.

## What a stranger sees

Three things travel from this machine to the public page, and each one broke
separately once.

**Finished runs.** Every forward run publishes itself to the mirror as it
completes, best effort — `_publish` never fails a backtest, and that is the
right trade. It also means the archive can silently fall behind, so
`quantlab publish` catches it up by asking the edge what it already has and
sending the rest. Run it after any period when the mirror was misconfigured.

**The heartbeat.** A fit is about thirteen of every fourteen minutes and
persists nothing: hundreds of evaluations, none of them a result, and one row
per genome per fold would bury the record it is supposed to be. So for most of
any minute there is genuinely no run to list, and the page said *nothing
running* through a night of forty-six iterations. The loop now writes what it is
doing to `loop_activity` — one row, rewritten — served at `/api/loop` locally
and pushed to the same path at the edge. The page renders it with a staleness
threshold, so a loop that died reads as died rather than as idle.

**The champion.** `best_2026` requires `trades > 0`. A configuration gated out
of the whole forward window finishes at exactly +0.00%, which outranks every
honest loss, and the public champion was a flat line on zero trades while
eighteen real results sat beneath it. Standing aside is not a result. The rule
is enforced identically in the store and in the Worker, because a champion that
differs between the two is a bug that only one visitor ever sees.

`loop_health.py` now checks the edge as well as this machine. Everything local
was green through that whole night — the loop was alive, the services were up,
the ledger was growing — because nothing was looking at what the public could
see.

## Configuration

    ANTHROPIC_API_KEY       enables the proposer
    ZAI_API_KEY             enables the GLM adversary
    QUANTLAB_CODEX          path to the codex binary (defaults to /Applications/…)
    QUANTLAB_CLUSTER=0      run without posting to or reading the Wall
    QUANTLAB_REPOSITORY_ROOT

All optional. With none of them set the loop still runs, on invention alone, and
says so in every record.
