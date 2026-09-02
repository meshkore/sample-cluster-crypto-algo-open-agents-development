"""Vector memory: what happened the last N times the market looked like this?

Operator idea A74 (2026-09-02): a vector database that helps the decision tree. The
trade ledger already produces its exact content - every decision bar carries the
20-feature A32 snapshot AND the outcome that followed (won / lost / unforced /
missed). Store those vectors; at a new candidate entry, retrieve the k nearest
historical situations and let their realised outcomes vote.

Why this is worth a slot next to the TCN and the tree. It is a THIRD inductive bias:
the net learns convolutions over a 96-bar window, the tree learns axis-aligned splits,
and this learns nothing at all - it remembers. Non-parametric and local, it is
strongest exactly where the other two are weakest, on rare configurations with few
training examples. And it is the only one of the three that can say *"I have never
seen anything like this"*: when the k-th neighbour is far away, that distance is an
honest abstention signal rather than a confident guess.

**The leakage rule, which is the whole ballgame.** A neighbour is admissible only if
its outcome had already RESOLVED strictly before the query bar. Nearest-neighbour
lookup is the easiest way in this codebase to read the future by accident: a neighbour
three bars ahead of the query, whose trade closed a week later, would hand the model
tomorrow's answer through a lookup table and every backtest would look brilliant. So
the index is built in expanding blocks - exactly the discipline `meta.py` uses - and a
query is only ever answered by an index frozen before its block began.

Nothing here decides. It reports `hit_rate`, `support` and `distance`; a module turns
those into a size multiplier or a veto, and the ordinary paired A/B decides adoption.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Store:
    """Historical decisions, sorted by the moment their outcome became knowable."""

    X: np.ndarray          # (n, F) standardised feature snapshots
    won: np.ndarray        # (n,) 1.0 if the decision worked out, 0.0 if it did not
    resolved_ns: np.ndarray  # (n,) when the outcome became knowable - NOT the entry
    mean: np.ndarray       # (F,) standardisation, kept so queries scale identically
    std: np.ndarray

    def __len__(self) -> int:
        return int(len(self.won))


def build_store(X: np.ndarray, won: np.ndarray, resolved_ns: np.ndarray) -> Store:
    """Standardise and sort by resolution time.

    Standardisation matters more than it looks: the A32 features mix bounded shapes
    (a candle body in [-1, 1]) with unbounded z-scores (volume_z), and a raw L2
    distance would let one loud feature define "similar" on its own.
    """
    X = np.asarray(X, dtype=np.float64)
    won = np.asarray(won, dtype=np.float64)
    resolved_ns = np.asarray(resolved_ns, dtype=np.int64)
    if not (len(X) == len(won) == len(resolved_ns)):
        raise ValueError("X, won and resolved_ns must describe the same rows")
    order = np.argsort(resolved_ns, kind="stable")
    X, won, resolved_ns = X[order], won[order], resolved_ns[order]
    mean = X.mean(axis=0) if len(X) else np.zeros(X.shape[1] if X.ndim > 1 else 0)
    std = X.std(axis=0) if len(X) else np.ones(X.shape[1] if X.ndim > 1 else 0)
    std = np.where(std < 1e-9, 1.0, std)
    return Store(X=(X - mean) / std, won=won, resolved_ns=resolved_ns,
                 mean=mean, std=std)


def query_blocks(store: Store, Q: np.ndarray, at_ns: np.ndarray, *, k: int = 25,
                 blocks: int = 12, min_support: int = 5) -> dict[str, np.ndarray]:
    """Answer every query from an index containing ONLY strictly-earlier outcomes.

    Queries are grouped into `blocks` chronological chunks. Each chunk is served by an
    index frozen at the chunk's start, so no query can ever see a neighbour that
    resolved after it - the cost being that a query late in a chunk is answered by a
    slightly stale memory, which is the conservative direction to err in.

    Returns per query: `hit_rate` (the neighbours' outcome rate), `support` (how many
    admissible neighbours were found), `distance` (mean distance to them, the
    familiarity signal) and `answered` (whether support cleared `min_support`).
    Unanswered queries are NaN, never a default - a memory with nothing to say must
    abstain rather than guess the base rate.
    """
    from sklearn.neighbors import NearestNeighbors

    Q = (np.asarray(Q, dtype=np.float64) - store.mean) / store.std
    at_ns = np.asarray(at_ns, dtype=np.int64)
    n = len(Q)
    hit = np.full(n, np.nan)
    dist = np.full(n, np.nan)
    support = np.zeros(n, dtype=np.int64)

    order = np.argsort(at_ns, kind="stable")
    for chunk in np.array_split(order, max(1, blocks)):
        if not len(chunk):
            continue
        cutoff = int(at_ns[chunk].min())
        usable = int(np.searchsorted(store.resolved_ns, cutoff, side="left"))
        if usable < min_support:
            continue
        kk = min(k, usable)
        nn = NearestNeighbors(n_neighbors=kk).fit(store.X[:usable])
        d, idx = nn.kneighbors(Q[chunk])
        hit[chunk] = store.won[:usable][idx].mean(axis=1)
        dist[chunk] = d.mean(axis=1)
        support[chunk] = kk

    answered = support >= min_support
    hit = np.where(answered, hit, np.nan)
    return {"hit_rate": hit, "distance": dist, "support": support, "answered": answered}


def summarise(result: dict[str, np.ndarray], won: np.ndarray) -> dict:
    """Does the memory actually separate winners from losers? One honest number.

    `edge` is the realised outcome rate of the queries the memory liked most minus the
    rate of those it liked least, measured on its own answered subset. A memory that
    remembers nothing useful reports an edge near zero, which is the result that
    retires the idea rather than a reason to tune it.
    """
    ok = result["answered"] & np.isfinite(result["hit_rate"])
    if ok.sum() < 20:
        return {"answered": int(ok.sum()), "edge": None,
                "note": "too few answered queries to say anything"}
    h, y = result["hit_rate"][ok], np.asarray(won, dtype=float)[ok]
    hi, lo = h >= np.quantile(h, 0.75), h <= np.quantile(h, 0.25)
    return {
        "answered": int(ok.sum()),
        "coverage": round(float(ok.mean()), 4),
        "top_quartile_rate": round(float(y[hi].mean()), 4),
        "bottom_quartile_rate": round(float(y[lo].mean()), 4),
        "base_rate": round(float(y.mean()), 4),
        "edge": round(float(y[hi].mean() - y[lo].mean()), 4),
        "median_distance": round(float(np.nanmedian(result["distance"][ok])), 4),
    }
