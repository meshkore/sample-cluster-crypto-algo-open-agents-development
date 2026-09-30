"""R(t): the causal region where the best trades live (S10-6).

The operator's idea, 2026-09-27: *"instead of applying it to the whole chart, to every
candle, to every moment of history, apply it only in the places and above all the CONDITIONS
in which 80% of the best trades have occurred."*

So the region is **fitted from the teacher, not from the learner's results**: run system 06's
zigzag oracle over the research years, take the top quantile of its swings by net return
after the 0.30% round trip, and ask which causal conditions hold on 80% of them. Everything
in that sentence is a constraint:

* **Causal.** The predicate reads only the frozen registry's market columns at the bar it
  judges. The oracle is hindsight and is the teacher; R must be computable live or it is
  not a region, it is a label.
* **Interpretable.** A shallow tree whose chosen leaves print as rules. The operator asked
  to see the conditions, and what R excludes has to be priceable.
* **Fitted on years <= N-1** for each walk-forward year N, like everything else here.
* **Wide enough to trade.** Coverage per year is a deliverable (see `tools/conditions.py`).

**What "a swing is inside R" means.** A causal reader cannot know the trough on the trough
bar - that is the oracle's privilege. So a swing counts as covered when R holds on any bar of
its *entry zone*: the trough and the `zone` bars after it (default 8, two hours). A region
that fires one hour into a three-day leg has found that leg; demanding the exact bottom
would be demanding hindsight.

**Version zero already exists and is scored first** by the tool: system 06's gates are a
hand-built region, and a learned region that cannot beat them has not earned the name.

This module is pure arithmetic over arrays - no data loading, no 2026, no model. The tool
that feeds it real bars is `research/system10/tools/conditions.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .features import MARKET

ROUND_TRIP = 0.003       # 10 bps commission + 5 bps slippage, each way
ORACLE_THRESHOLD = 0.03  # system 06's shipped zigzag threshold (engine config `threshold`)
ENTRY_ZONE = 8           # bars after the trough during which finding the swing still counts


def up_swings(close: np.ndarray, threshold: float = ORACLE_THRESHOLD,
              cost: float = ROUND_TRIP) -> np.ndarray:
    """Every trough-to-peak leg of 06's oracle as rows (start, end, net return).

    Net is peak / trough - 1 - the round trip: what the perfect trader earned on that leg
    after the toll a real trade pays.
    """
    from system006_oracle_net_15m.oracle import zigzag_pivots

    pivots = zigzag_pivots(close, threshold)
    rows = [(a.index, b.index, b.price / a.price - 1.0 - cost)
            for a, b in zip(pivots, pivots[1:]) if a.kind == "low" and b.kind == "high"]
    return np.array(rows, dtype=float).reshape(-1, 3)


def entry_zone_mask(n: int, swings: np.ndarray, zone: int = ENTRY_ZONE) -> np.ndarray:
    """True on the bars where entering still catches one of `swings`."""
    mask = np.zeros(n, dtype=bool)
    for start, end, _ in swings:
        s = int(start)
        mask[s:min(s + zone, int(end), n)] = True
    return mask


def swings_covered(inside: np.ndarray, swings: np.ndarray, zone: int = ENTRY_ZONE) -> np.ndarray:
    """Per swing: does the region hold on any bar of its entry zone?"""
    out = np.zeros(len(swings), dtype=bool)
    for k, (start, end, _) in enumerate(swings):
        s = int(start)
        out[k] = bool(inside[s:min(s + zone, int(end), len(inside))].any())
    return out


@dataclass
class Region:
    """A shallow tree and the leaves chosen to cover the target share of best swings."""

    tree: object
    leaves: list[int]
    coverage_target: float
    fitted_on: list[int]
    quantile: float
    net_floor: float                      # the top-quantile swing's minimum net return
    train_bar_share: float = 0.0
    train_swing_coverage: float = 0.0
    leaf_stats: list[dict] = field(default_factory=list)

    def holds(self, X: np.ndarray) -> np.ndarray:
        """R per bar. Rows with any non-finite feature (warm-up) are outside."""
        ok = np.isfinite(X).all(axis=1)
        out = np.zeros(len(X), dtype=bool)
        if ok.any():
            leaf = self.tree.apply(X[ok].astype(np.float32))
            out[ok] = np.isin(leaf, self.leaves)
        return out

    def rules(self) -> list[str]:
        """Each chosen leaf as the conjunction of thresholds on its path."""
        t = self.tree.tree_
        paths: dict[int, list[str]] = {}

        def walk(node: int, conds: list[str]) -> None:
            if t.children_left[node] == t.children_right[node]:
                paths[node] = conds
                return
            name, thr = MARKET[t.feature[node]], float(t.threshold[node])
            walk(t.children_left[node], conds + [f"{name} <= {thr:.4g}"])
            walk(t.children_right[node], conds + [f"{name} > {thr:.4g}"])

        walk(0, [])
        return [" AND ".join(paths[leaf]) or "(every bar)" for leaf in self.leaves]


def fit(X: np.ndarray, zone: np.ndarray, swing_ids: np.ndarray, n_swings: int,
        coverage: float = 0.8, depth: int = 4, fitted_on=(), quantile: float = 0.2,
        net_floor: float = 0.0, max_rows: int = 600_000, seed: int = 0) -> Region:
    """Fit R on pooled training bars.

    `X` is the pooled market matrix, `zone` marks bars inside a best swing's entry zone,
    and `swing_ids` gives, per bar, the id of the best swing whose zone it is in (-1
    otherwise), so coverage is counted in *swings*, not bars. The tree separates zone bars
    from the rest; its leaves are then taken in order of zone density until the chosen
    set's union covers `coverage` of the swings. Density first means the region is as
    narrow as it can be for the coverage it promises - its width is then reported, never
    assumed.
    """
    from sklearn.tree import DecisionTreeClassifier

    ok = np.isfinite(X).all(axis=1)
    idx = np.flatnonzero(ok)
    rng = np.random.default_rng(seed)
    if len(idx) > max_rows:
        # Keep every zone bar; subsample the rest. The tree only has to learn the shape
        # of the boundary, and class_weight rebalances what the subsample distorts.
        pos, neg = idx[zone[idx]], idx[~zone[idx]]
        keep = max(max_rows - len(pos), 1)
        neg = rng.choice(neg, size=min(keep, len(neg)), replace=False)
        sample = np.sort(np.concatenate([pos, neg]))
    else:
        sample = idx
    tree = DecisionTreeClassifier(max_depth=depth, min_samples_leaf=0.01,
                                  class_weight="balanced", random_state=seed)
    tree.fit(X[sample].astype(np.float32), zone[sample])

    leaf_all = np.full(len(X), -1, dtype=np.int64)
    leaf_all[ok] = tree.apply(X[ok].astype(np.float32))
    stats = []
    for leaf in np.unique(leaf_all[ok]):
        in_leaf = leaf_all == leaf
        ids = np.unique(swing_ids[in_leaf & (swing_ids >= 0)])
        stats.append({"leaf": int(leaf), "bars": int(in_leaf.sum()),
                      "density": float(zone[in_leaf].mean()), "swings": set(ids.tolist())})
    stats.sort(key=lambda s: -s["density"])

    chosen, covered, bars = [], set(), 0
    for s in stats:
        if n_swings and len(covered) / n_swings >= coverage:
            break
        chosen.append(s["leaf"])
        covered |= s["swings"]
        bars += s["bars"]
    region = Region(tree=tree, leaves=chosen, coverage_target=coverage,
                    fitted_on=sorted(int(y) for y in fitted_on), quantile=quantile,
                    net_floor=float(net_floor),
                    train_bar_share=bars / max(int(ok.sum()), 1),
                    train_swing_coverage=len(covered) / max(n_swings, 1))
    region.leaf_stats = [{"leaf": s["leaf"], "bar_share": s["bars"] / max(int(ok.sum()), 1),
                          "density": round(s["density"], 4), "chosen": s["leaf"] in chosen}
                         for s in stats]
    return region


def holds(region: Region, X: np.ndarray) -> np.ndarray:
    """R per bar for a fitted region; causal because X is."""
    return region.holds(X)
