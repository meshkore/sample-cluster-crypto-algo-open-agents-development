"""THE PANEL: the only thing a model should ever see.

A panel is a `(len(days), len(streams))` matrix in which cell (k, j) is stream j as it was
knowable on day k, put through the transform that makes it stationary. Three properties are
guaranteed rather than hoped for:

  * causal - built through `clock.asof`, which cannot return a row published after the day;
  * stationary by default - each stream carries its own default transform in the registry;
  * honest about absence - a stream with no reading yet is NaN, never zero and never the
    first value it will eventually have. `coverage()` reports how much of each column is
    real, because a feature that is 80% NaN is a feature that will be learned as a date.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np

from . import clock, store, transform
from .streams import get, registry


@dataclass
class Panel:
    days: list[str]
    names: tuple[str, ...]
    values: np.ndarray            # (len(days), len(names)) float32, NaN where unknown
    coverage: dict[str, float]    # per stream: fraction of days with a real reading

    def __len__(self) -> int:
        return len(self.days)

    def column(self, name: str) -> np.ndarray:
        return self.values[:, self.names.index(name)]

    def drop_sparse(self, minimum: float = 0.5) -> "Panel":
        """Keep only columns that are actually present for at least `minimum` of the days.

        This is not tidiness. A macro series that starts in 2020 inside a record that starts
        in 2017 hands the model a column that is NaN for exactly the early era - and a model
        with a NaN-fill learns "this is the old regime" from the fill itself.
        """
        keep = [i for i, n in enumerate(self.names) if self.coverage[n] >= minimum]
        return Panel(self.days, tuple(self.names[i] for i in keep),
                     self.values[:, keep],
                     {self.names[i]: self.coverage[self.names[i]] for i in keep})

    def filled(self, value: float = 0.0) -> np.ndarray:
        out = self.values.copy()
        out[~np.isfinite(out)] = value
        return out


def build(days: list[str], streams: list[str] | None = None, *,
          sealed: bool = False, transforms: dict[str, str] | None = None,
          skip_missing: bool = True) -> Panel:
    """Assemble a panel. `streams` defaults to everything registered AND built.

    `transforms` overrides the registry's default per stream, which is how the same series
    can be a level in one study and a sixty-day change in another without either of them
    redefining what the series IS.
    """
    wanted = streams if streams is not None else sorted(registry())
    names, cols, cover = [], [], {}
    for sid in wanted:
        if not store.have(sid):
            if skip_missing:
                continue
            raise FileNotFoundError(f"{sid} is registered but not built")
        stream = get(sid)
        raw = clock.history(sid, days, sealed=sealed)
        how = (transforms or {}).get(sid, stream.transform)
        col = transform.apply(how, raw, days=days)
        names.append(sid)
        cols.append(col)
        cover[sid] = float(np.isfinite(col).mean()) if len(col) else 0.0
    if not cols:
        return Panel(days, (), np.zeros((len(days), 0), dtype=np.float32), {})
    return Panel(days, tuple(names),
                 np.asarray(np.column_stack(cols), dtype=np.float32), cover)


def signature(days: list[str], names: tuple[str, ...]) -> str:
    """A content hash of what a panel WAS, so a cached result can be proved to match.

    Every cache bug this laboratory has had came from a cache key that described the request
    and not the data. This one describes the data.
    """
    parts = []
    for n in names:
        entry = store.read_manifest().get("streams", {}).get(n, {})
        parts.append(f"{n}:{entry.get('sha256', '?')}")
    blob = json.dumps({"days": [days[0], days[-1], len(days)] if days else [],
                       "streams": parts}, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
