"""Meta-labelling for system 06: a verdict on each entry the primary would take.

Lopez de Prado's meta-labelling (AFML ch. 3) splits a strategy in two: a PRIMARY
decides the side, a SECONDARY decides whether to act, and how big. Here the primary
is the ensemble's own entry rule — the net's conviction clears `enter` and the slow
trend is up — and this file fits the secondary: an XGBoost classifier that, at each
candidate bar, predicts which triple barrier the trade hits (target / stop / timeout)
and turns that into an expected net return. The ensemble's `meta` module then refuses
candidates whose expected net is below a margin.

Why it is the right lever here: every earlier idea raised the trade count, and at a
30 bps round trip that is a guaranteed cost against an uncertain gain. A filter is the
only change that can raise the return and LOWER the bill at once — and it attacks
drawdown directly by declining the entries most likely to stop out.

**Honesty (a tradeable claim, not a study).** Verdicts come from an EXPANDING,
time-purged walk-forward: a candidate's verdict is issued by a model trained only on
candidates whose labels RESOLVED before that candidate's entry — never on its future,
never on another symbol's future at the same wall-clock time. Overlapping labels are
purged by resolution time and a bar embargo drops the adjacency band. The earliest
block has no out-of-sample model, so those candidates get NO verdict and the module
abstains on them (the primary stands) rather than trading on a leaked one. Only the
sealed 2026 candidates are scored by the final research model, which never saw them.

The candidate set is read straight from `signals.npz` (prob ≥ enter ∧ trend up), so the
net is not re-run: the verdicts are one small `.npz` an operator can inspect.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from quantlab_ml.labels import Barriers, net_of_costs, realised_volatility, triple_barrier
from quantlab_ml.model import CLASSES, build_classifier, expected_net

from . import universe
from .dataset import LOCK, Dataset

ROUND_TRIP = 0.003  # 10 bps commission + 5 bps slippage each side — the project invariant
VOL_SPAN = 96       # ~1 day at 15m, for the barrier volatility estimate
FEATURE_NAMES = ["prob", "vol_ratio", "momentum", "trend", "vol_level",
                 "ret_1", "ret_16", "ret_96", "drawdown_96"]
WARMUP = 96         # bars of history a feature row needs


def _ns(ts: datetime) -> int:
    naive = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return int(np.datetime64(naive, "ns").astype("int64"))


def _trailing_max(x: np.ndarray, span: int) -> np.ndarray:
    """Causal rolling maximum over `span` bars (C-fast via pandas)."""
    import pandas as pd

    return pd.Series(x).rolling(span, min_periods=1).max().to_numpy()


@dataclass
class Candidates:
    """Every entry the primary would take, pooled across symbols, in time order."""

    X: np.ndarray            # (n, F) features
    y: np.ndarray            # (n,) triple-barrier class in {-1,0,1}
    ret: np.ndarray          # (n,) net return actually earned by the resolution
    entry_ns: np.ndarray     # (n,) entry time (epoch ns)
    resolve_ns: np.ndarray   # (n,) time the label resolved (epoch ns) — for purging
    sigma: np.ndarray        # (n,) horizon-scaled vol at entry — prices expected_net
    symbol: np.ndarray       # (n,) symbol string, to write verdicts back per symbol


def gather_candidates(
    dataset: Dataset, signals: str, symbols: list[str], *,
    enter: float = 0.5, target: float = 2.0, stop: float = 1.0, horizon: int = 96,
) -> Candidates:
    """Build the pooled candidate table: features, triple-barrier labels, purge times."""
    data = np.load(signals)
    combined = dataset.combined()
    barriers = Barriers(target=target, stop=stop, horizon=horizon)
    scale = np.sqrt(max(horizon, 1))

    cols: dict[str, list] = {k: [] for k in
                             ("X", "y", "ret", "entry_ns", "resolve_ns", "sigma", "symbol")}
    for sym in symbols:
        bars = combined.get(sym)
        if not bars or f"{sym}__epoch_ns" not in data.files:
            continue
        close = np.array([b.close for b in bars], dtype=float)
        high = np.array([b.high for b in bars], dtype=float)
        low = np.array([b.low for b in bars], dtype=float)
        bar_ns = np.array([_ns(b.timestamp) for b in bars], dtype=np.int64)

        vol = realised_volatility(close, span=VOL_SPAN)
        tb = triple_barrier(high, low, close, vol, barriers)
        ret_net = net_of_costs(tb["ret"], ROUND_TRIP)
        tmax = _trailing_max(close, 96)

        sig_ns = data[f"{sym}__epoch_ns"].astype(np.int64)
        prob = data[f"{sym}__prob"].astype(float)
        trend = (data[f"{sym}__trend"].astype(np.int8) if f"{sym}__trend" in data.files
                 else np.ones(len(sig_ns), dtype=np.int8))
        volr = (data[f"{sym}__vol"].astype(float) if f"{sym}__vol" in data.files
                else np.ones(len(sig_ns)))
        mom = (data[f"{sym}__mom"].astype(float) if f"{sym}__mom" in data.files
               else np.zeros(len(sig_ns)))

        # Map every signal bar to its position in the bar series, then keep only the
        # ones that map exactly, cleared warm-up, resolved a barrier, and are primary
        # candidates (conviction up, trend up). All signal arrays share the sig_ns index.
        pos = np.clip(np.searchsorted(bar_ns, sig_ns), 0, len(bar_ns) - 1)
        match = bar_ns[pos] == sig_ns
        keep = match.copy()
        keep[match] &= (pos[match] >= WARMUP) & tb["touched"][pos[match]]
        keep &= (prob >= enter) & (trend == 1)
        idx = np.where(keep)[0]      # indices into the signal arrays
        p = pos[idx]                  # matching bar positions
        if not len(p):
            continue
        feats = np.column_stack([
            prob[idx], volr[idx], mom[idx], trend[idx].astype(float),
            vol[p] * scale,
            close[p] / close[p - 1] - 1.0,
            close[p] / close[p - 16] - 1.0,
            close[p] / close[p - 96] - 1.0,
            close[p] / np.maximum(tmax[p], 1e-12) - 1.0,
        ])
        cols["X"].append(feats)
        cols["y"].append(tb["label"][p].astype(int))
        cols["ret"].append(ret_net[p])
        cols["entry_ns"].append(sig_ns[idx])
        cols["resolve_ns"].append(bar_ns[np.clip(tb["ends_at"][p], 0, len(bar_ns) - 1)])
        cols["sigma"].append(vol[p] * scale)
        cols["symbol"].append(np.array([sym] * len(p)))

    if not cols["X"]:
        raise ValueError("no candidates found — check the signals file and enter threshold")
    X = np.vstack(cols["X"])
    order = np.argsort(np.concatenate(cols["entry_ns"]), kind="stable")  # time order
    return Candidates(
        X=X[order],
        y=np.concatenate(cols["y"])[order],
        ret=np.concatenate(cols["ret"])[order],
        entry_ns=np.concatenate(cols["entry_ns"])[order],
        resolve_ns=np.concatenate(cols["resolve_ns"])[order],
        sigma=np.concatenate(cols["sigma"])[order],
        symbol=np.concatenate(cols["symbol"])[order],
    )


def _fit_predict(Xtr, ytr, Xte, sigma_te, target, stop, seed=42):
    """One classifier fold: fit on the past, return expected-net verdicts for the test."""
    present = sorted({int(v) for v in ytr})
    encode = {label: i for i, label in enumerate(present)}
    model = build_classifier(seed=seed)
    model.fit(Xtr, np.array([encode[int(v)] for v in ytr]))
    narrow = model.predict_proba(Xte)
    probs = np.zeros((len(narrow), len(CLASSES)))
    for label, col in encode.items():
        probs[:, CLASSES.index(label)] = narrow[:, col]
    return expected_net(probs, sigma_te, target, stop, ROUND_TRIP)


def build_verdicts(
    cand: Candidates, *, target: float = 2.0, stop: float = 1.0,
    folds: int = 6, embargo_bars: int = 96, bar_seconds: int = 900, min_train_frac: float = 0.2,
) -> tuple[dict[str, dict[int, float]], dict[str, Any]]:
    """Expanding, time-purged verdicts for research; the final model scores 2026.

    Returns `(per_symbol {entry_ns: expected_net}, document)`. Candidates in the
    first (train-only) block get no verdict — the module abstains on them.
    """
    lock_ns = _ns(datetime.fromisoformat(LOCK))
    embargo_ns = embargo_bars * bar_seconds * 1_000_000_000
    is_research = cand.entry_ns < lock_ns
    r = np.where(is_research)[0]
    f = np.where(~is_research)[0]
    verdicts: dict[str, dict[int, float]] = {}
    covered = 0

    def emit(rows, values):
        nonlocal covered
        for row, val in zip(rows, values):
            verdicts.setdefault(str(cand.symbol[row]), {})[int(cand.entry_ns[row])] = float(val)
            covered += 1

    n = len(r)
    min_train = int(n * min_train_frac)
    span = max(1, (n - min_train) // folds)
    fold_docs = []
    for k in range(folds):
        a = min_train + k * span
        b = n if k == folds - 1 else a + span
        if a >= n:
            break
        test_rows = r[a:b]
        t0 = cand.entry_ns[r[a]]  # entry time of the first test candidate
        train_mask = (cand.resolve_ns[r[:a]] < t0) & (cand.entry_ns[r[:a]] < t0 - embargo_ns)
        train_rows = r[:a][train_mask]
        if len(train_rows) < max(200, min_train // 4):
            continue
        values = _fit_predict(cand.X[train_rows], cand.y[train_rows], cand.X[test_rows],
                              cand.sigma[test_rows], target, stop)
        emit(test_rows, values)
        fold_docs.append({"fold": k, "train": int(len(train_rows)), "test": int(len(test_rows)),
                          "purged_embargoed": int(a - len(train_rows))})

    # The sealed half: train on all research candidates whose labels resolved before
    # the lock, score 2026. The only model allowed to speak about 2026.
    if len(f):
        train_mask = cand.resolve_ns[r] < lock_ns
        train_rows = r[train_mask]
        values = _fit_predict(cand.X[train_rows], cand.y[train_rows], cand.X[f],
                              cand.sigma[f], target, stop)
        emit(f, values)

    document = {
        "candidates": int(len(cand.y)),
        "research": int(n), "forward": int(len(f)),
        "covered": covered, "uncovered_research": int(n - (covered - len(f))),
        "positive": int(sum(1 for m in verdicts.values() for v in m.values() if v > 0)),
        "folds": fold_docs, "features": FEATURE_NAMES,
        "barriers": {"target": target, "stop": stop}, "round_trip": ROUND_TRIP,
    }
    return verdicts, document


def write_meta(verdicts: dict[str, dict[int, float]], out_path: str) -> None:
    """Write the per-symbol verdict channel to an .npz the Channels loader reads."""
    payload: dict[str, np.ndarray] = {}
    for sym, table in verdicts.items():
        if not table:
            continue
        ns = np.array(sorted(table), dtype=np.int64)
        payload[f"{sym}__meta_ns"] = ns
        payload[f"{sym}__meta"] = np.array([table[int(x)] for x in ns], dtype=np.float32)
    np.savez(out_path, **payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--signals", default="research/system06/signals.npz")
    parser.add_argument("--out", default="research/system06/meta.npz")
    parser.add_argument("--enter", type=float, default=0.5)
    parser.add_argument("--target", type=float, default=2.0)
    parser.add_argument("--stop", type=float, default=1.0)
    parser.add_argument("--horizon", type=int, default=96)
    args = parser.parse_args(argv)

    symbols = [s for s in args.symbols.split(",") if s] if args.symbols else universe.load()
    dataset = Dataset(args.data_root, symbols=symbols, interval=args.interval)
    print("gathering candidates ...", flush=True)
    cand = gather_candidates(dataset, args.signals, symbols, enter=args.enter,
                             target=args.target, stop=args.stop, horizon=args.horizon)
    print(f"  {len(cand.y):,} candidates ({int((cand.entry_ns < _ns(datetime.fromisoformat(LOCK))).sum()):,} research)")
    print("fitting the time-purged walk-forward + final model ...", flush=True)
    verdicts, document = build_verdicts(cand, target=args.target, stop=args.stop)
    write_meta(verdicts, args.out)
    Path(args.out).with_suffix(".json").write_text(json.dumps(document, indent=1, default=str))
    print(json.dumps({k: v for k, v in document.items() if k not in ("folds", "features")}, indent=1))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
