---
id: WORLD-1
title: "The World Archive: skeleton, registry, clock, and adoption of everything already on disk"
status: active
priority: high
owner: win-opus-5
category: trading-system
initiative: world-archive
created: 2026-09-15
updated: 2026-09-15
tags: [world, macro, catalogue, point-in-time, news, reusable]
blocks: [WORLD-2, WORLD-3, WORLD-4, WORLD-5]
---

## What was asked

The operator, 2026-09-15: *"Este modelo de comportamiento de la economía a nivel mundial
quiero que lo estructures de forma excelente... probablemente lo vamos a extraer y lo vamos a
colocar dentro del sistema de backtesting... es un almacén de datos de todas las noticias del
pasado ordenadas por orden cronológico. El valor de todos los assets, de todos los
indicadores... lo podremos aprovechar mil y una veces."*

## What was built

`trading-system/quantlab_world/` — design in `quantlab_world/docs/DESIGN.md`.

| module | what it owns |
|---|---|
| `streams.py` | the registry: 83 streams, each with category, region, unit, frequency, publication lag, stamp convention, expiry and source. A stream with no declared lag cannot be registered. |
| `clock.py` | `asof` / `history` / `staleness` / `audit`. The only path to a value, and it filters on `known_at`. |
| `store.py` | append-only JSON per stream, JSONL per year for events, a manifest with digests. Gitignored. |
| `panel.py` | `(days × streams)` matrices, causal, stationary by default, honest about absence. |
| `transform.py` | one named function per way of making a series usable; calendar-true lookbacks. |
| `events.py` | the chronicle — tier 1 curated, tier 2 feeds, `pressure()` turns events into a stream. |
| `adapters.py` | adoption of the existing catalogue; `raw` adopts anything an ingest run writes. |
| `ingest/dbnomics.py` | IMF monthly CPI, free and keyless. |
| `inventory.py` | coverage by category and region, the clock table, the stale table, the gaps. |

## Three defects it caught on its first run

1. **The period stamp.** FRED stamps a monthly CPI on the *first* of the month it describes.
   Adding the publication lag to that stamp made February's inflation knowable on 19 February;
   it is published in March. `Stream.known_at` now waits for the period to *end* first, and
   `lag_days` is measured from the period end, which is how release calendars are written.
2. **Row lookbacks.** A year-on-year change computed as "365 rows back" is a year only on a
   daily grid. On a 24-row panel it was silently all-NaN. Lookbacks are now calendar days.
3. **Stale readings standing for the present.** An as-of reader carries the last observation
   forward forever. FRED stopped mirroring the OECD's national inflation series — **Japan ends
   2021-06, Korea 2023-11, China/India/Brazil/UK/Turkey/South Africa 2025-03..04** — so a 2026
   evaluation was about to be fed five-year-old Japanese inflation as though it were current.
   Every stream now expires; past its expiry it returns None and its column is NaN.

## The inflation problem, stated honestly

Free, current, prompt monthly inflation for the whole world does not exist without a key.
Measured on 2026-09-15:

| region | best free source | current to |
|---|---|---|
| US | FRED `CPIAUCSL` | last month — good |
| euro area, European members, Turkey | Eurostat `prc_hicp_manr` (keyless JSON) | current — good |
| JP CN IN BR ZA KR CA GB | IMF via DBnomics (keyless) | 2025-06/07 — about a year behind |
| everywhere else | World Bank | annual only |

So the archive uses what is current, marks the rest expired, and leans on the channel that
*is* daily, current and genuinely regional for every one of those countries: **the currency,
the local bond and the local equity market**. What a holder in São Paulo faces shows up in
USD/BRL today; inflation is the slow confirmation that arrives a quarter later.

## Done when

- [x] registry, clock, store, panel, transforms, chronicle, inventory
- [x] adoption of the catalogue with no new downloads — 73 streams, 325,615 observations,
      earliest 1947-01-01
- [x] IMF inflation ingest for the regions FRED abandoned
- [ ] `WORLD-2` system 09's `world.py` becomes a view over the archive, its private lag table
      deleted rather than duplicated, and the regional block priced on the held-back year
- [ ] `WORLD-3` chronicle completed and every entry verified
- [ ] `WORLD-4` Eurostat + GDELT + Wikipedia attention ingests
- [ ] `WORLD-5` extraction into the backtester
