---
id: world-archive
title: "The World Archive: a chronological, point-in-time record of the world, shared by every system"
status: active
priority: high
oneliner: "One package that answers 'what did the world look like on day D, to someone standing on day D' - every published number and every event, stamped with both the date it describes and the date it became knowable, owned by no system and reusable by all of them."
modules: [trading-system]
target: "quantlab_world extracted cleanly enough to move into the backtester as a directory move; system 09's world.py becomes a view over it"
created: 2026-09-15
updated: 2026-09-15
owner: win-opus-5
related: [system-nine-reality-alignment, global-market-trend]
---

## Why this initiative exists

The operator, 2026-09-15: *"Este modelo de comportamiento de la economía a nivel mundial
quiero que lo estructures de forma excelente. No solo va a formar parte ya de este sistema de
trading, sino que probablemente lo vamos a extraer y lo vamos a colocar dentro del sistema de
backtesting. Porque igualmente puede servir para cualquier sistema futuro. Piensa que al final
es un almacén de datos de todas las noticias del pasado ordenadas por orden cronológico. El
valor de todos los assets, de todos los indicadores. Entonces, una vez tengamos todo eso, lo
podremos aprovechar mil y una veces."*

He is naming the same defect twice in this laboratory's history. The first time it was the
price candles and the external feeds sitting inside `research/system06/`, which is what
`quantlab_catalog` was built to fix. This is the second and larger instance: the macro layer
now lives inside `quantlab_system09/world.py`, it loads its own series, it applies its own
publication lags from its own private table, and it will die with the system that happens to
contain it — exactly as system 08's work did when system 08 was closed on 2026-09-14.

There is also a correctness argument that is stronger than the tidiness one. **The publication
lag is the product.** A macro feature read on its reference date rather than its release date
is a leak, it does not announce itself, and it makes results better — which is the worst
possible combination. Today that lag is a convention every consumer must remember. In the
archive it is structural: the store writes `known_at` into every row, and the only path to a
value goes through it.

## What it is

`trading-system/quantlab_world/` — design in `quantlab_world/docs/DESIGN.md`. Two record
shapes and nothing else: an **observation** (`stream_id, ref_date, known_at, value, vintage`)
and an **event** (`ref_ts, known_at, category, jurisdiction, entities, headline, weight`).
Four pillars: the registry (code, committed), the clock (as-of, enforced), the store
(append-only, never committed), the panel (stationary by default).

Its only dependencies are the standard library, numpy, and — for adopting what is already on
disk — `quantlab_catalog`. It does not know a trading system exists. Extraction is a directory
move and an import rename, deliberately.

## What it buys

- **System 09 immediately.** The market-direction head needs inflation and real rates *by
  region*, which is what it lacked when it scored −0.23% mean edge across the selection years.
- **Every future system.** A world, on a clock, on day one, with the expensive half already
  paid for.
- **The question we have never been able to answer**: *was the model wrong, or was the world
  surprising?* The surprises become a dated, weighted series rather than a story told
  afterwards.

## Done when

1. `python -m quantlab_world.build` adopts every series already in the catalogue — ~100
   streams, no new downloads — and `inventory` prints coverage and gaps by region.
2. `quantlab_system09/world.py` is a thin view over `quantlab_world.panel`, with its private
   lag table deleted rather than duplicated.
3. The chronicle (tier 1) is complete for 2013-2026 and every entry is `verified`.
4. GDELT tone and Wikipedia attention land as ordinary streams (tier 2).
5. An ablation prices the regional block on the held-back year, against the same bar as
   everything else in system 09: does it survive a year nobody selected on.

## Tasks

`WORLD-1` skeleton and adoption · `WORLD-2` system 09 migration · `WORLD-3` the chronicle ·
`WORLD-4` tier-2 feeds · `WORLD-5` extraction to the backtester.
