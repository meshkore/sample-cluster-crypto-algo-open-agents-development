"""The tradable universe, frozen to a file so a run is reproducible.

Selection - the turnover screen, the stablecoin exclusion, the listing-age filter - is
`quantlab_system06.universe`, which talks to Binance and writes a snapshot. This module
only READS the snapshot, which is why it lives here: the list a system trades is shared
data, and every system re-implementing its own load is how one of them ends up with a
different universe than the run it is being compared against.

THE FAILURE THIS GUARDS. `universe.load()` used to fall back to a single symbol when the
file could not be found, which happens whenever a tool is run from anywhere but the repo
root. Nothing raised. An afternoon of A/B results came back roughly 24x too weak and
looked like a refuted idea rather than a broken path. So this refuses instead: a
universe that is missing or degenerate is an exception, never a default.
"""

from __future__ import annotations

import json

from .paths import universe_file

MIN_SYMBOLS = 5


def load_universe(name: str = "universe.json") -> list[str]:
    path = universe_file(name)
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. The universe is a frozen snapshot, not a default - "
            f"re-select it deliberately with `python -m quantlab_system06.universe`.")
    data = json.loads(path.read_text(encoding="utf-8"))
    symbols = data.get("symbols") if isinstance(data, dict) else data
    if not isinstance(symbols, list) or len(symbols) < MIN_SYMBOLS:
        raise ValueError(
            f"degenerate universe in {path}: {symbols!r}. A single-symbol fallback once "
            f"made an afternoon of A/B results read 24x too weak; it raises now.")
    return [str(s) for s in symbols]
