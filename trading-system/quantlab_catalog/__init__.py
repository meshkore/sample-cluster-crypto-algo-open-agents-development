"""The shared data catalogue: one door to everything a new system is allowed to start from.

Operator, 2026-09-08: "todo eso que es informacion, precalculo de indicadores,
normalizacion de datos, todo eso forma parte del CATALOGO COMUN del que tiene que
disponer cualquier nueva estrategia que vayamos a disenar."

He is naming a real defect. The price candles were already shared - every system reads
them through `quantlab_backtester.data.FocusedDataset` - but everything else this
laboratory has downloaded ended up inside ONE system's folder:

    research/system06/universe.json          the tradable universe snapshot
    research/system06/external/              funding, Fear & Greed, on-chain, FRED
    backtester/data/indicators/system06/     the cached indicator panels

So a new system had exactly two options, and both are wrong: reach into system06's
folders (which couples the two and means deleting one breaks the other), or download
seven years of history again. This package is the third option. It owns the canonical
locations, it knows the legacy ones, and it is the only import a new system needs to
reach any data this lab already paid for.

WHAT IS ACTUALLY HERE, measured rather than assumed - run `python -m
quantlab_catalog.inventory` for the live version, which prints sizes and coverage and,
just as importantly, prints what is MISSING:

    price     27 Binance USDT pairs, 15m, split research (<2026) / forward (2026 sealed)
    external  perp funding (14 symbols), Fear & Greed (daily from 2018-02),
              4 on-chain series, 7 FRED reference markets
    derived   per-system indicator caches and standardiser fits

NOT here, and no amount of reading this file will make it appear: 1h candles, 5m
candles, order-book depth, and news text. Those have never been downloaded on this
machine. `inventory` says so out loud, because a catalogue that lets you believe in data
it does not have is worse than no catalogue.

THE RULES THIS PACKAGE ENFORCES, because they are the ones that have cost us:

  * the 2026 lock is structural, not a convention. `research()` cannot return a 2026
    bar. Ask for the sealed window explicitly and the ask is visible in the diff.
  * external series carry their own publication lag. The catalogue hands back the raw
    series with its timestamps untouched; applying the lag is the consumer's job and
    `reference.SERIES_LAG_DAYS` is where the measured delays live.
  * nothing here downloads. Fetching is a deliberate act with its own entry point, so
    that no backtest can quietly reach the internet halfway through a run.
"""

from __future__ import annotations

from .paths import (CATALOG_ROOT, DATA_ROOT, EXTERNAL_DIR, INDICATOR_ROOT, LOCK,
                    UNIVERSE_DIR, indicator_dir, external_file, universe_file)
from .candles import INTERVALS, candles, forward, research
from .external import (EXTERNAL_SERIES, etf_flows, feargreed, funding, onchain,
                       reference_markets, series_status, stablecoins)
from .universe import load_universe

__all__ = [
    "CATALOG_ROOT", "DATA_ROOT", "EXTERNAL_DIR", "INDICATOR_ROOT", "LOCK",
    "UNIVERSE_DIR", "indicator_dir", "external_file", "universe_file",
    "INTERVALS", "candles", "research", "forward",
    "EXTERNAL_SERIES", "feargreed", "funding", "onchain", "reference_markets",
    "series_status", "load_universe", "stablecoins", "etf_flows",
]
