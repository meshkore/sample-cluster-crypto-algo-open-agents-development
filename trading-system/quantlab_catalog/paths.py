"""Where the shared data lives, and where it used to live.

Every path in this laboratory has been written as a bare string at the point of use,
which is why the same data ended up under three different roots. This module is the one
place that knows a location, so moving a store is an edit here rather than a search.

LEGACY FALLBACKS ARE DELIBERATE AND TEMPORARY. The external feeds were downloaded into
`research/system06/external/` before a shared catalogue existed. `external_file()`
returns the canonical path when the file is there and the legacy path when it is not, so
a machine that has not migrated keeps working and a migrated one never looks back. When
`inventory` reports no legacy hits on any machine we care about, the fallback goes.
"""

from __future__ import annotations

import os
from pathlib import Path

# The repository root, found by walking up from this file rather than by assuming a
# working directory. Tools in this lab are run from the repo root by convention and from
# somewhere else by accident, and the accident used to produce an empty universe and a
# silent fallback to a single symbol - a whole afternoon of results that were 24x too
# weak. QUANTLAB_ROOT overrides it for anyone vendoring this package elsewhere.
_HERE = Path(__file__).resolve()
REPO_ROOT = Path(os.environ.get("QUANTLAB_ROOT") or _HERE.parents[2])

# The shared data root. Everything under it is gitignored and re-downloadable.
DATA_ROOT = REPO_ROOT / "trading-system" / "backtester" / "data"
CATALOG_ROOT = DATA_ROOT

# Non-price series: funding, Fear & Greed, on-chain, reference markets.
EXTERNAL_DIR = DATA_ROOT / "external"
# Universe snapshots. A run must be reproducible, so the tradable list is frozen to a
# file and re-selected only on purpose.
UNIVERSE_DIR = DATA_ROOT / "universe"
# Cached indicator panels, still namespaced per system: they are derived under a
# system's own feature definitions and are not interchangeable. Sharing the CACHE would
# be a correctness bug, not an economy.
INDICATOR_ROOT = DATA_ROOT / "indicators"

# The sealed forward window. Structural, not a convention: `candles.research()` cannot
# return a bar at or after this instant.
LOCK = "2026-01-01T00:00:00+00:00"

# Where each store lived before the catalogue existed.
_LEGACY_EXTERNAL = REPO_ROOT / "research" / "system06" / "external"
_LEGACY_UNIVERSE = REPO_ROOT / "research" / "system06"


def external_file(name: str) -> Path:
    """The canonical path for an external series file, or the legacy one if only it exists."""
    canonical = EXTERNAL_DIR / name
    if canonical.exists():
        return canonical
    legacy = _LEGACY_EXTERNAL / name
    return legacy if legacy.exists() else canonical


def universe_file(name: str = "universe.json") -> Path:
    canonical = UNIVERSE_DIR / name
    if canonical.exists():
        return canonical
    legacy = _LEGACY_UNIVERSE / name
    return legacy if legacy.exists() else canonical


def indicator_dir(system: str, phase: str = "research") -> Path:
    """The indicator cache for one system and one era. Created on demand by its writer."""
    if phase not in ("research", "combined", "forward"):
        raise ValueError(f"unknown phase {phase!r}; expected research, combined or forward")
    return INDICATOR_ROOT / system / phase


def legacy_hits() -> dict[str, list[str]]:
    """What is still only in a pre-catalogue location. Empty means migration is done."""
    out: dict[str, list[str]] = {}
    if _LEGACY_EXTERNAL.is_dir():
        stale = [p.name for p in sorted(_LEGACY_EXTERNAL.glob("*.json"))
                 if not (EXTERNAL_DIR / p.name).exists()]
        if stale:
            out["external"] = stale
    if (_LEGACY_UNIVERSE / "universe.json").exists() and \
            not (UNIVERSE_DIR / "universe.json").exists():
        out["universe"] = ["universe.json"]
    return out
