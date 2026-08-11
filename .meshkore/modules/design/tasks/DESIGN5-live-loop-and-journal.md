---
id: DESIGN5
title: "Watch the loop run: a circular live diagram, and a journal of every event"
status: done
priority: high
owner: master
category: design
initiative: public-agent-lab
created: 2026-08-11
updated: 2026-08-11
tags: [ui, monitor, live, websocket, observability, journal]
depends_on: [DESIGN4, DOCS1]
blocks: []
---

## Scope

Two halves of one thing the operator asked for.

**One:** a page that shows the loop working — the orchestrator's pieces and its
agents, drawn as a cycle, updating as it runs, left open on a screen.

**Two:** observability. Every construction should leave a diary of what happened
along the way — the messages, the advice, the refusals — so it is possible to
ask whether this loop is genuinely exploring or is boxed into a shape where it
cannot produce a disruptive idea, whether it tests enough, whether it adjusts
values or fires one hypothesis and stops.

## Delivered

- `/live`, reached from a small door in the thin top bar. Seven boxes on a
  circle, starting up-left and turning clockwise, in a square — the shape is the
  claim that this ends where it began. Each box carries what is happening in it
  right now, written from the event's own payload rather than a label.
- The seven are `ResearchLoop.NODE_ORDER`, the same seven as the architecture
  doc. `STAGE_NODES` maps stages to boxes in Python, so a new stage cannot
  silently light nothing.
- The hub shows the hypothesis id, the iteration, and the claim the proposer
  actually made. FIT carries an inner dotted loop for the genetic search, which
  is where most of every hour goes.
- COMPOSE is not labelled "write the code". The loop composes expression trees
  the grammar validates. Relabelling it would misdescribe the guarantee that
  makes an unattended loop safe.
- **The journal**: every event of a hypothesis, in order, appended to
  `loop/journal/<id>.jsonl` and kept — stages, generations, advisor replies and
  refusals, every backtest. Served at `/api/journal[/<id>]` and `/api/journals`,
  rendered as a diary beside the diagram, with a picker for past hypotheses.
- `consulted` now carries what came back: which advisors answered, which
  refused, how many peer replies, whether the proposer was the one allowed to
  search the web, the claim, and the seed rules that survived the grammar. That
  is the payload the "is it exploring or circling" question is asked of.
- Two transports, one contract. The daemon serves a hand-rolled RFC 6455 socket
  at `/ws` that **tails the journal file** — so the observer cannot slow the
  research, cannot lose an event, and replays the whole hypothesis to a browser
  arriving late. The public mirror polls, because nothing on the internet may
  open a connection back to the laboratory. The page asks `/health` which
  architecture it is in instead of learning it from a failed handshake.

## Verified

Playwright, against the running loop, on both surfaces. Local: websocket, seven
boxes, seven arcs, `frame → consult → compose` walked live, journal growing, no
page errors. Public: polling, same diagram, same walk, `fit` lit with real
backtest results arriving, no page errors.

## Acceptance criteria

- The diagram is a square cycle starting up-left and turning clockwise.
- A box lights as the loop enters it and says what is happening inside it.
- Every event of every hypothesis is recorded and readable, however long.
- The live page works on the public site with no socket available.
