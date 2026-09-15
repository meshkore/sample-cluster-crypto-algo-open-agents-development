"""ADOPTION, NOT COPYING: readers that turn what is already on disk into observations.

On day one the archive downloads nothing. Every series this laboratory has already paid for
is declared in the registry with an adapter here, so the World Archive starts with roughly a
hundred streams and an empty download queue. New sources get a new function in this file and
a new row in `streams.py`; nothing else changes.

Each adapter returns the same thing - `[(ref_date, value), ...]`, ascending, deduplicated,
with the date being what the number DESCRIBES. Turning that into what was KNOWABLE is
`clock.py`'s job and no adapter may do it, because a lag applied in two places is a lag
applied twice and a lag applied nowhere looks exactly the same from here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

Obs = list[tuple[str, float]]


def _cat():
    """The trading laboratory's catalogue, imported ONLY when adopting from it.

    The archive has been moved out of that repository and must be readable without it; the
    dependency survives in one direction and at one moment - the build, which turns the
    catalogue's files into stamped observations. After that the store stands alone.
    """
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[3] / "trading-system"
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import quantlab_catalog
    return quantlab_catalog


def _day(t_s: float) -> str:
    return datetime.fromtimestamp(float(t_s), tz=timezone.utc).date().isoformat()


def _clean(rows: list[tuple[str, float]]) -> Obs:
    """Ascending, one value per day, finite. The last reading of a day wins."""
    seen: dict[str, float] = {}
    for day, value in rows:
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if v != v:                       # NaN, which FRED emits as "." and json as null
            continue
        seen[day] = v
    return [(d, seen[d]) for d in sorted(seen)]


# ------------------------------------------------------------------------------- readers
def fred(series_id: str) -> Obs:
    raw = _cat().reference_markets().get(series_id)
    if not raw:
        return []
    return _clean([(str(d)[:10], v) for d, v in raw.get("rows", []) if v is not None])


def feargreed() -> Obs:
    return _clean([(_day(r["t_s"]), r["value"]) for r in _cat().feargreed() if "t_s" in r])


def onchain(name: str) -> Obs:
    return _clean([(_day(r["t_s"]), r["value"]) for r in _cat().onchain(name) if "t_s" in r])


def stablecoins() -> Obs:
    return _clean([(_day(r["t_s"]), r["value"]) for r in _cat().stablecoins() if "t_s" in r])


def etf_flows() -> Obs:
    return _clean([(_day(r["t_s"]), r["value"]) for r in _cat().etf_flows() if "t_s" in r])


def open_interest(symbol: str) -> Obs:
    return _clean([(_day(r["t_s"]), r["value"]) for r in _cat().open_interest(symbol)
                   if "t_s" in r])


def funding(symbol: str) -> Obs:
    """Settlements are three times a day; the archive stores the day's total cost of carry."""
    per_day: dict[str, float] = {}
    for r in _cat().funding(symbol):
        t = r.get("t_ms")
        if t is None:
            continue
        per_day[_day(float(t) / 1000.0)] = per_day.get(
            _day(float(t) / 1000.0), 0.0) + float(r.get("rate", 0.0))
    return [(d, per_day[d]) for d in sorted(per_day)]


def price(symbol: str) -> Obs:
    """Daily close, from the 15-minute tape, sealed window included.

    The archive stores everything it has; refusing to look past the lock is the READER's job
    (`asof` and `panel` take `sealed=`), not the store's. A store that cannot hold 2026 could
    never be used to evaluate 2026 at all.
    """
    bars = _cat().candles([symbol], include_sealed=True).get(symbol, [])
    per_day: dict[str, float] = {}
    for b in bars:
        ts = getattr(b, "timestamp", None)
        close = getattr(b, "close", None)
        if ts is None or close is None:
            continue
        per_day[ts.astimezone(timezone.utc).date().isoformat()] = float(close)
    return [(d, per_day[d]) for d in sorted(per_day)]


def global_cap() -> Obs:
    """The sector's capitalisation, summed from per-asset published caps.

    CoinGecko's historical global endpoint is paid, so this is reconstructed: the sum of the
    published capitalisations we do hold. It covers less than the whole market - system 09
    measured its universe at ~94% of the published global figure - and it is therefore an
    INDEX OF THE SECTOR rather than the sector's total. Registered as such; the difference
    matters to a level and not at all to a rate of change, which is how it is consumed.
    """
    assets = _cat().market_cap_full().get("assets", {})
    per_day: dict[str, float] = {}
    for blob in assets.values():
        for day, metrics in blob.get("days", {}).items():
            v = metrics.get("CapMrktCurUSD") or metrics.get("CapMrktEstUSD")
            if v:
                per_day[day] = per_day.get(day, 0.0) + float(v)
    return [(d, per_day[d]) for d in sorted(per_day)]


def raw(source: str, name: str) -> Obs:
    """Whatever an ingest run wrote under `world/raw/<source>/<name>.json`.

    The general mechanism for every future source. An ingest module's only contract is to
    write `{"meta": {...}, "rows": [[day, value], ...]}` there; the registry then declares a
    stream over it with a lag and a transform, and nothing else in the package changes.
    """
    from .store import WORLD_ROOT
    p = WORLD_ROOT / "raw" / source / f"{name}.json"
    if not p.is_file():
        raise FileNotFoundError(
            f"{p} has not been harvested. Run `python -m mwmodel.archive.ingest.{source}` - "
            "fetching is always a deliberate command, never a side effect of reading.")
    blob = json.loads(p.read_text(encoding="utf-8-sig"))
    return _clean([(str(d)[:10], v) for d, v in blob.get("rows", [])])


#: The registry names its reader by string so that `streams.py` stays importable without
#: touching the catalogue, and so an unknown reader is caught at build time.
READERS = {
    "fred": fred, "feargreed": feargreed, "onchain": onchain, "stablecoins": stablecoins,
    "etf_flows": etf_flows, "open_interest": open_interest, "funding": funding,
    "price": price, "global_cap": global_cap, "raw": raw,
}


def read(stream) -> Obs:
    fn = READERS.get(stream.reader)
    if fn is None:
        raise KeyError(f"stream {stream.id!r} names reader {stream.reader!r}, "
                       f"which does not exist; have {sorted(READERS)}")
    return fn(*stream.reader_args)
