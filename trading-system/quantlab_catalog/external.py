"""Everything in the catalogue that is not a price candle.

Four families, all public, all free, all already downloaded on this machine:

  funding      Binance USD-M perpetual funding rates, 8h cadence, per symbol.
               The crowd-positioning signal. `fundingTime` is the SETTLEMENT
               timestamp - a bar may only read settlements strictly before it.
  feargreed    alternative.me Fear & Greed, daily from 2018-02. Published each
               morning; a bar may only read days strictly past.
  onchain      blockchain.info daily series - unique addresses, transactions,
               hash rate, miners' revenue. Network USE rather than price, which is
               the only reason they are here: they are not another moving average
               of the thing we are trying to predict.
  reference    FRED daily macro - NASDAQ, VIX, 2y and 10y yields, the 2s10s curve,
               the broad dollar, WTI. Non-revised series only, each with a MEASURED
               publication delay in `quantlab_system06.reference.SERIES_LAG_DAYS`.

THE ONE RULE THAT MATTERS, and it is the consumer's job rather than this module's:
every one of these is published LATE. This module hands back the series with its own
timestamps untouched and applies no lag, no resample and no fill, because a helper that
silently shifted a series would be indistinguishable from a helper that leaked the
future. `reference.py` is where the measured delays live and where a test fails if
reality drifts past what is assumed.

Nothing here downloads. `quantlab_system06.external_data.harvest` fetches; this reads.
That separation is why no backtest in this laboratory can reach the internet halfway
through a run.
"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import EXTERNAL_DIR, external_file

# family -> (filename pattern, one line on what it is)
EXTERNAL_SERIES: dict[str, tuple[str, str]] = {
    "funding": ("funding_{symbol}.json", "Binance perp funding, 8h, per symbol"),
    "feargreed": ("feargreed.json", "alternative.me Fear & Greed, daily from 2018-02"),
    "onchain": ("chain_{name}.json", "blockchain.info daily network series"),
    "reference": ("reference_markets.json", "FRED daily macro, non-revised only"),
}
ONCHAIN_SERIES = ("n-unique-addresses", "n-transactions", "hash-rate", "miners-revenue")


def _read(path: Path):
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is not in the catalogue. Run the harvest deliberately - nothing "
            f"in quantlab_catalog downloads.")
    return json.loads(path.read_text(encoding="utf-8"))


def funding(symbol: str) -> list[dict]:
    """Funding settlements for one symbol, verbatim, ascending by `fundingTime`."""
    return _read(external_file(f"funding_{symbol}.json"))


def feargreed() -> list[dict]:
    return _read(external_file("feargreed.json"))


def onchain(name: str) -> list[dict]:
    if name not in ONCHAIN_SERIES:
        raise ValueError(f"unknown on-chain series {name!r}; have {ONCHAIN_SERIES}")
    return _read(external_file(f"chain_{name}.json"))


def reference_markets() -> dict:
    """The FRED bundle, keyed by series id, each with its own `rows` of [date, value]."""
    return _read(external_file("reference_markets.json"))


def series_status() -> dict[str, dict]:
    """What is present, how big, and where it was found. Used by `inventory`.

    Reports the LOCATION as well as the size because the difference between a
    catalogue path and a legacy one is the difference between migrated and not, and a
    machine can be half-migrated without anything failing.
    """
    out: dict[str, dict] = {}
    seen: set[Path] = set()
    for fam, (pattern, what) in EXTERNAL_SERIES.items():
        if "{symbol}" in pattern:
            files = sorted(EXTERNAL_DIR.glob("funding_*.json"))
            legacy = [p for p in (external_file(f"funding_{s}.json")
                                  for s in _known_funding_symbols()) if p.is_file()]
            files = sorted({*files, *legacy})
        elif "{name}" in pattern:
            files = [external_file(f"chain_{n}.json") for n in ONCHAIN_SERIES]
            files = [p for p in files if p.is_file()]
        else:
            p = external_file(pattern)
            files = [p] if p.is_file() else []
        seen.update(files)
        out[fam] = {
            "what": what,
            "files": len(files),
            "bytes": sum(p.stat().st_size for p in files),
            "in_catalogue": all(EXTERNAL_DIR in p.parents for p in files) if files else None,
            "example": str(files[0]) if files else None,
        }
    return out


def _known_funding_symbols() -> list[str]:
    """Symbols with a funding file, discovered from disk rather than declared.

    A hard-coded list would go stale the first time the universe is re-selected, and
    would then report a symbol as missing data when the truth is that nobody looked.
    """
    names: set[str] = set()
    for root in (EXTERNAL_DIR, external_file("funding_BTCUSDT.json").parent):
        if root.is_dir():
            names.update(p.name[len("funding_"):-len(".json")]
                         for p in root.glob("funding_*.json"))
    return sorted(names)
