---
title: "The shared data catalogue"
category: context
updated: 2026-09-08
owner: master
status: active
---

# The shared data catalogue

**Every new trading system starts here.** Read this before downloading anything, and
before writing a loader. Nothing in this laboratory needs to fetch history twice.

```python
import quantlab_catalog as cat

symbols = cat.load_universe()          # the frozen tradable list
bars    = cat.research(symbols)        # every bar strictly before 2026 — cannot leak
sealed  = cat.forward(symbols)         # the 2026 window, alone, deliberately
fng     = cat.feargreed()              # daily crowd sentiment from 2018-02
macro   = cat.reference_markets()      # FRED: VIX, NASDAQ, DXY, WTI, 2y/10y, curve
```

```bash
python -m quantlab_catalog.inventory   # what exists, sizes, and WHAT IS MISSING
python -m quantlab_catalog.prune       # report redundant cache copies (--apply deletes)
```

## Why it exists

The price candles were always shared. Everything else this lab downloaded ended up
inside **one system's folder** — the universe snapshot, the funding history, Fear &
Greed, the on-chain series, the FRED bundle, all under `research/system06/`. A new
system therefore had two options and both were wrong: reach into system06's directory
(coupling them, so deleting one breaks the other), or re-download seven years of
history.

`quantlab_catalog` is the third option. It owns the canonical locations, knows the
legacy ones, and is the only import a new system needs to reach any data already paid
for.

## What is in it

| family | what | coverage |
|---|---|---|
| price | Binance USDT spot, **15m only** | 27 symbols, research (2017-08 → 2025-12-31) and forward (2026, sealed) |
| universe | the frozen tradable list | 14 symbols, re-selected only on purpose |
| funding | Binance USD-M perp funding, 8h | 14 symbols |
| feargreed | alternative.me index, daily | 3,128 days from 2018-02 |
| onchain | blockchain.info daily | unique addresses, transactions, hash rate, miners' revenue |
| reference | FRED daily macro, **non-revised series only** | 11 series incl. VIX, NASDAQ, DXY, WTI, DGS2/DGS10, T10Y2Y |
| derived | cached indicator panels | per system — **not interchangeable**, they encode that system's feature definitions |

## What is NOT in it

Naming these is the point of the catalogue. A queued experiment once waited weeks on
data nobody had.

- **1h candles** — never downloaded. The 15m series can be resampled; that is not the
  same thing as an independently sourced hourly bar, and a resample inherits every gap.
- **5m candles** — `quantlab_intraday`'s timeframe; its cache is not on this machine.
- **order-book depth** — no venue feed has ever been ingested. The participation cap in
  the backtester is a *modelled* constraint, not measured depth.
- **news text** — no feed, no archive, no vendor. The nearest thing here is Fear &
  Greed, which is a sentiment *index*, not news.
- **macro vintages** — FRED is here; ALFRED (point-in-time revisions) is not.

## The three rules the catalogue enforces

1. **The 2026 lock is structural, not a convention.** `research()` cannot return a
   sealed bar — the loader stops at the lock and the wrapper re-checks it. Reading 2026
   is a separate call that shows up in a diff.
2. **External series carry their own publication lag.** The catalogue returns raw
   timestamps with no shift, resample or fill; applying the lag is the consumer's job.
   The measured delays live in `quantlab_system06.reference.SERIES_LAG_DAYS` and a test
   fails when reality drifts past them. A helper that silently shifted a series would be
   indistinguishable from one that leaked the future.
3. **Nothing in the catalogue downloads.** Fetching is a deliberate act with its own
   entry point, so no backtest can reach the internet halfway through a run.

## The cache leak, and why `prune` is a tool

`inventory` found the sealed 2026 window — eight months — occupying **9.1 GB** against
403 MB for 2018–2025. Backwards by a factor of twenty-three.

The cause is a content-addressed cache doing exactly what it was told: the key hashes
the request, and a forward request ends at *now*, so every refresh produced a new hash
and a fresh copy of nearly the same file. BTCUSDT alone had **385 copies**; 5,646 across
27 symbols. Research ends at the lock, which never moves, so research had exactly one.

Nothing was corrupt — they were valid re-downloads with a slightly later right edge.
The prune keeps the newest per symbol/interval/era and reclaimed **9.1 GB**. It is a
tool rather than a one-off delete because the leak recurs with every forward refresh.

## Adding to the catalogue

A new feed belongs here — not in a system folder — the moment a *second* system could
plausibly want it. Add the fetcher wherever it is used, point its output at
`quantlab_catalog.paths.EXTERNAL_DIR`, give it an entry in `EXTERNAL_SERIES`, and state
its publication lag next to the data rather than in a comment somewhere downstream.
