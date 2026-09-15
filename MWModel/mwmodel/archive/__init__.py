"""THE WORLD ARCHIVE: what the world looked like on day D, to someone standing on day D.

A library, not a strategy. It answers one question and answers it the same way for every
system that will ever ask it, which is the entire reason it is a separate package: system 08
was closed on 2026-09-14 and its data should never have been inside it.

    import mwmodel.archive as W

    W.asof("us.rate.2y", "2023-06-14")          # knowable that day, or None
    W.panel(days, W.by_category("inflation"))   # (days x streams), lagged and stationary
    W.events(since="2022-11-01", until="2022-11-30")
    W.coverage()                                # what is here, what is missing, by region

WHAT MAKES IT DIFFERENT FROM A FOLDER OF JSON
Every observation carries two dates: the one it describes and the one it became knowable. A
reader cannot reach the first without going through the second. March's inflation is a fact
about March that nobody had until April, and a model that reads it on 31 March is reading the
future - an error that does not announce itself, because it makes the results better.

THE INVARIANTS, enforced rather than documented:
  1. nothing here downloads at read time; fetching is `python -m mwmodel.archive.ingest.<src>`
  2. `asof(D)` never returns an observation with known_at > D
  3. a stream with no declared publication lag cannot be registered at all
  4. the sealed 2026 window needs an explicit `sealed=True`, so crossing it shows in a diff
  5. no observation file is ever committed; the registry and the chronicle are
  6. sources that disagree are stored as disagreeing, never silently reconciled

Design and build order: `docs/DESIGN.md`.
"""

from __future__ import annotations

from .clock import SealedWindowError, asof, audit, history, staleness, window
from .events import CHRONICLE, Event, between as events, pressure
from .panel import Panel, build as panel
from .store import LOCK_DAY, WORLD_ROOT, build_all, built, read_manifest
from .streams import (CATEGORIES, FREQUENCIES, REGIONS, Stream, TRANSFORMS, by_category,
                      by_region, get, registry)

__all__ = [
    "asof", "window", "history", "staleness", "audit", "SealedWindowError",
    "panel", "Panel",
    "events", "pressure", "Event", "CHRONICLE",
    "registry", "get", "by_category", "by_region", "Stream",
    "CATEGORIES", "REGIONS", "FREQUENCIES", "TRANSFORMS",
    "build_all", "built", "read_manifest", "WORLD_ROOT", "LOCK_DAY",
    "coverage",
]


def coverage() -> dict:
    """What the archive actually holds, per category and per region, and what it is missing.

    Deliberately blunt about absence. A catalogue that lets you believe in data it does not
    have is worse than no catalogue - system 06 learned that with a silent fallback to a
    single symbol and an afternoon of results that were twenty-four times too weak.
    """
    from .streams import registry as _reg
    from . import store as _store

    manifest = _store.read_manifest()
    entries = manifest.get("streams", {})
    out: dict = {"streams_registered": len(_reg()), "streams_built": len(entries),
                 "by_category": {}, "by_region": {}, "missing": manifest.get("missing", {}),
                 "built_at": manifest.get("built_at")}
    for sid, s in _reg().items():
        for axis, key in (("by_category", s.category), ("by_region", s.region)):
            slot = out[axis].setdefault(key, {"registered": 0, "built": 0, "rows": 0,
                                              "earliest": None})
            slot["registered"] += 1
            e = entries.get(sid)
            if e:
                slot["built"] += 1
                slot["rows"] += e.get("rows", 0)
                first = e.get("first")
                if first and (slot["earliest"] is None or first < slot["earliest"]):
                    slot["earliest"] = first
    return out
