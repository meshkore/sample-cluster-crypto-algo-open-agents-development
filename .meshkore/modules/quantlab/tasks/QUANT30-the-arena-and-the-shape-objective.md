---
id: QUANT30
title: "Score the curve someone could have bought into, and let the search run itself"
status: in-progress
priority: critical
owner: master
category: quantlab
initiative: self-improving-arena
created: 2026-08-15
updated: 2026-08-15
tags: [objective, drawdown, machine-learning, unattended, meta-labelling, 2026]
depends_on: [QUANT28, QUANT29]
blocks: [QUANT31]
---

# The shape objective, and the arena that searches on it

## Why

Every ranking in this laboratory measured total return, which answers exactly one
question: what happened to the person who bought on day one. The operator pointed
at the champion's equity curve — flat for three years, everything earned in 2021,
a quarter given back from the peak, four consecutive losing months, ending below
its own high — and asked what happens to whoever bought at the top. They lose
everything the strategy ever made.

And the laboratory had to keep working unattended, without a language model in
the loop.

## What is running right now

    screen -S quantlab-arena        # the supervisor, arena-forever.sh
    tail -f research/agent_runs/arena/arena.log
    touch research/agent_runs/arena/arena.stop     # to stop it

Each round: fit a surrogate on the archive, rank 1,500 proposals, measure 40 (30
model-chosen, 10 random immigrants). A genome beating the champion's screen
fitness by 10% — and enduring the era, and holding at least 15 sealed trades —
triggers two real backtests, then a meta-label fit for that genome, then the same
two backtests again with the filter on. Four cards on the public board per
promotion, capped at four promotions a day.

## Resuming on a different machine

Four things do NOT travel with the repository, and only one of them is a problem.

1. **`backtester/data/` — 32 GB of five-minute bars, gitignored.** Without it the
   arena cannot load a tape and will not start. Fetch with the documented
   downloader (`quantlab download BTCUSDT --interval 5m ...`, public Binance spot
   API) for the twelve symbols in `hypothesis_scan.SYMBOLS`, into `research/` and
   `forward/`. This is the only real cost of moving machines.
2. **`research/agent_runs/arena/` — the archive, champion and meta tables.** A
   fresh machine starts with an empty archive and re-derives the champion floor
   from `INCUMBENT_SIGNAL` in about two seconds. The surrogate's memory rebuilds
   in ten minutes of searching. Nothing here needs carrying across.
3. **`.meshkore/credentials/` — the mirror token.** Without it the arena still
   runs and still records every measurement in the local database; it just prints
   "no public mirror configured" instead of publishing. Research is unaffected.
4. **`.meshkore/log/` — the daily narrative.** Gitignored by the standard's
   deny-list. Everything load-bearing from it is in `PLANNING.md` and in these
   task files, which do travel.

Then: `orchestrator-manager/scripts/arena-forever.sh`, ideally under `screen` or
`nohup` so it survives the terminal.

## Where it is applied

`quality.py` is imported by exactly three things and there is no fourth:
`hypothesis_scan.money` (fits stop/stake/vol-target on it),
`Orchestrator._publish` (stamps it on every run reaching the mirror), and the
Cloudflare Worker (crowns the board on it, with return as a fallback for rows
published before it existed). Before 2026-08-15 it was a module with fourteen
tests and zero importers.

## Corrections this needed, each pinned by a test

1. **A growth term deaf above +300%.** It divided by 3.0, so +353% and +6,000%
   both scored a flat 1.0 — against a requirement the operator had already
   stated in as many words. Log scale now.
2. **A twelve-month floor** made every sealed run score exactly zero, which reads
   as worthless and means short. Six.
3. **A rule that cannot be judged forward is not a candidate.** The arena's first
   rounds found genomes at 0.535 and 0.566 that would take between zero and four
   trades in 2026 and could never be promoted. A training-side frequency proxy
   was tried and failed — the gate closes the book through a falling year, so 40
   trades a year in training became 1–4 in the sealed window. The term measures
   the sealed COUNT directly, which is evidence-existence, never evidence-content.
4. **Abstentions were topping the board.** The Worker crowned on `trades > 0`; a
   one-trade run would have taken the title. Fifteen now, matching
   `hypothesis_scan.survives` and the arena's `judgeable` term.
5. **The screen marked equity only at trade events**, so a position bleeding away
   from a high was invisible until it exited. Open positions are revalued daily
   (SCREEN_VERSION 5). Its first cut opened the curve on the first ENTRY, a day
   already carrying that position's round trip, so `final_return` disagreed with
   `Walk.return_pct` by up to 8e-4 and `maximum_drawdown` was measured from a
   peak the account never had. Opens at par now; sixteen real walks agree to 1e-15.
6. **A 139-second margin on a 90-minute model fit.** The first real meta-label fit
   took 5,261s against a 5,400s timeout — on the shortest horizon in the grid, on
   a machine also running this loop's backtests. Three hours now, and a fit over
   70% of budget says so in the log while still succeeding.

## What it has established

- The edge decayed at the end of 2024: six promoted systems, six triggers, all
  positive 2018–2024, all negative in 2025, all negative in 2026.
- Filters are four for four: every one improves training and hollows out 2026.
  The purpose-fitted meta-label is the cleanest evidence because its control ran
  beside it — training quality 0.000 → 0.380 with the drawdown halved and 186
  fewer trades, and 2026 went from 17 sealed trades to 4.
- The screen does not predict the engine: six comparisons, five collapse to zero,
  `unlucky` is the killer every time.

## Rules this work must not break

- 2026 is a locked forward evaluation. The single sanctioned use is the sealed
  trade COUNT — how much evidence exists, never what it says.
  `test_the_trade_COUNT_is_the_only_channel_from_the_sealed_tape` enforces it
  structurally rather than by reading the code.
- Both halves or nothing: identical parameters except `trade_from`.
- Long-only, research-only. No live orders, wallets or exchange secrets.
- No headless agents, no `claude -p`, nothing outside the operator's terminal.
