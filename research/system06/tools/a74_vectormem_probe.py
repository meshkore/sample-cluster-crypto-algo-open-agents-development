"""P53 stage 1: does the vector memory know anything the tree does not?

The module (quantlab_system06/vectormem.py) was built and tested on 2026-09-02 and
then never referenced by anything - a finished third inductive bias that has never
influenced a decision or produced a number. Before wiring it into the orchestrator,
its own docstring names the test it must pass: "a memory that remembers nothing
useful reports an edge near zero, which is the result that retires the idea rather
than a reason to tune it."

So this asks the purest form of the question, with no backtest in the loop:

  for every decision bar (the tree's own 20-feature A32 snapshot), retrieve the
  k nearest PAST situations whose outcome had already resolved, and let their
  realised outcomes vote. Does that vote separate the bars that went on to win
  from the bars that went on to lose?

Outcome = the tree's own label: forward HORIZON-bar (8h) return positive. Using the
tree's features AND the tree's label is the point, not a shortcut - the kill
criterion for P53 is "carries nothing beyond the tree", so the memory is measured on
exactly the tree's ground, and a parametric baseline (logistic regression, SAME
expanding-block protocol, SAME index rows) is run beside it. Three verdicts can come
out, and two of them retire something:

  memory edge ~ 0                       -> the idea retires, module gets deleted
  memory edge > 0 but <= parametric     -> memory is a worse tree; retires too
  memory edge > parametric              -> it knows something local the fit misses;
                                           wire it as a module and run the paired A/B

Anti-leak: neighbours are admissible only when resolved_ns < the query block's start
(vectormem.query_blocks enforces this in expanding blocks). The one soft spot is that
build_store standardises features over ALL rows including future ones - scale
statistics, not outcomes, and the parametric baseline standardises identically, so
the comparison is fair even where the absolute number is a shade optimistic.

Bars are strided (default every 4th) to keep k-NN tractable beside six optimiser
workers; the stride is a fixed lattice, not a random sample, so reruns reproduce.

Run from the repo root: PYTHONPATH=trading-system python research/system06/tools/a74_vectormem_probe.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from quantlab_system06 import tree, vectormem
from quantlab_system06.dataset import Dataset

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
STRIDE = 4          # every 4th decision bar; lattice, reproducible
K = 25
BLOCKS = 12
BAR_NS = 15 * 60 * 1_000_000_000
RESOLVE_NS = tree.HORIZON * BAR_NS      # a label resolves HORIZON bars after its bar


def _pool() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    symbols = json.loads((ROOT / "_w192/config.json").read_text())["symbols"]
    research = Dataset(DATA, symbols=symbols, interval="15m").research()
    Xs, ys, ns_ = [], [], []
    for s in symbols:
        bars = research.get(s) or []
        X, y, ns, _fwd = tree.build_features(bars)
        keep = np.flatnonzero(y >= 0)[::STRIDE]
        if not len(keep):
            continue
        Xs.append(X[keep]); ys.append(y[keep]); ns_.append(ns[keep])
        print(f"  {s:>9}: {len(keep):,} decision bars", flush=True)
    X = np.concatenate(Xs); y = np.concatenate(ys); ns = np.concatenate(ns_)
    order = np.argsort(ns, kind="stable")
    return X[order], y[order].astype(float), ns[order]


def _parametric_baseline(store, X, y, at_ns, blocks: int) -> dict[str, np.ndarray]:
    """A logistic fit under the memory's exact protocol: same admissible index rows
    per block, same standardisation, predicting the same outcome. This is what
    'the tree' would squeeze out of these features parametrically."""
    from sklearn.linear_model import LogisticRegression

    Q = (np.asarray(X, dtype=np.float64) - store.mean) / store.std
    prob = np.full(len(Q), np.nan)
    order = np.argsort(at_ns, kind="stable")
    for chunk in np.array_split(order, max(1, blocks)):
        if not len(chunk):
            continue
        cutoff = int(at_ns[chunk].min())
        usable = int(np.searchsorted(store.resolved_ns, cutoff, side="left"))
        if usable < 200 or len(set(store.won[:usable].tolist())) < 2:
            continue
        clf = LogisticRegression(max_iter=500, C=1.0)
        clf.fit(store.X[:usable], store.won[:usable])
        prob[chunk] = clf.predict_proba(Q[chunk])[:, 1]
    answered = np.isfinite(prob)
    return {"hit_rate": prob, "distance": np.full(len(Q), np.nan),
            "support": answered.astype(np.int64) * 999, "answered": answered}


def main() -> int:
    print("pooling the champion universe through tree.build_features ...", flush=True)
    X, y, ns = _pool()
    print(f"pooled: {len(X):,} decision bars, base rate {y.mean():.4f}", flush=True)

    store = vectormem.build_store(X, y, ns + RESOLVE_NS)
    print(f"store built; querying {BLOCKS} expanding blocks, k={K} ...", flush=True)
    mem = vectormem.query_blocks(store, X, ns, k=K, blocks=BLOCKS)
    mem_verdict = vectormem.summarise(mem, y)
    print("memory   :", json.dumps(mem_verdict), flush=True)

    par = _parametric_baseline(store, X, y, ns, BLOCKS)
    par_verdict = vectormem.summarise(par, y)
    print("logistic :", json.dumps(par_verdict), flush=True)

    out = {
        "id": "A74-probe", "at": datetime.now(timezone.utc).isoformat(),
        "n_queries": int(len(X)), "stride": STRIDE, "k": K, "blocks": BLOCKS,
        "outcome": f"tree label: forward {tree.HORIZON}-bar return > 0",
        "memory": mem_verdict, "parametric_same_protocol": par_verdict,
        "kill_criterion": "memory edge ~0, or <= the parametric edge, retires the idea",
        "note": "diagnosis only; 2026 excluded by construction (research bars end 2025)",
    }
    dest = ROOT / "rnd" / f"a74_vectormem_probe_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
