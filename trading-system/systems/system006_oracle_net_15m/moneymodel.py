"""The learned money-management channel: per-bar size multipliers from trade history.

Operator idea A45. The champion's edge is thin on average (+0.17% per trade) but
strongly state-dependent: top-quartile entry-volatility trades earn +0.83pp more
than bottom-quartile, momentum +0.70pp, model probability +0.58pp — each several
times the average trade's entire expectancy, and the gradients hold in essentially
every research year individually. A walk-forward model of "state → per-trade net",
mapped to size multipliers, lifted capital-normalised expectancy ~45% relative in
5 of 7 out-of-sample years and never cost more than a rounding error in the rest.

This module makes that a channel, following `tree.py`'s honesty contract exactly:

  - TRADES for training come from simulating the champion's own entry/exit rule
    per symbol over the RESEARCH years (strictly pre-lock closes).
  - Each research year's bars are scored by a model fitted only on trades that
    completed strictly BEFORE that year, with the December before it embargoed
    (a trade opened in December can close inside the test year — leakage).
  - Early years without enough history get NO verdict: the module abstains there
    rather than guesses.
  - The sealed window is scored by a model fitted on research trades only.

The prediction is mapped to multipliers {0.5, 0.75, 1.0, 1.5, 2.0} by the TRAIN
fold's own quintile boundaries, so nothing about the scored year shapes its own
sizing. The output overlay (`{sym}__size_ns`, `{sym}__size`) attaches to the
channel table like meta/micro/tree, and the `sizing` module reads it only when
the `money_model` lever is on.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from .dataset import Dataset
from quantlab_catalog.paths import workspace as _workspace

FEATURES = ("prob", "vol", "mom", "hurst", "feargreed", "sweep", "breadth", "trend_age")
MULTS = np.array([0.5, 0.75, 1.0, 1.5, 2.0])
MIN_TRAIN_TRADES = 500
CLIP = 0.20   # clip the per-trade target so one moonshot year cannot dominate the fit
TOLL = 0.003


def train_mask(years: np.ndarray, months: np.ndarray, test_year: int) -> np.ndarray:
    """Trades usable to fit the model that scores `test_year`.

    Strictly earlier years, minus the December immediately before — a trade opened
    there can close inside the test year, which would leak outcome information."""
    return (years < test_year) & ~((years == test_year - 1) & (months == 12))


def mults_from_preds(pred: np.ndarray, train_pred: np.ndarray) -> np.ndarray:
    """Map predictions to size multipliers via the TRAIN fold's quintile bounds."""
    bounds = np.quantile(train_pred, [0.2, 0.4, 0.6, 0.8])
    return MULTS[np.searchsorted(bounds, pred)]


def _trend_age(trend: np.ndarray) -> np.ndarray:
    """Bars since the uptrend began, causal (0 while the trend is down)."""
    age = np.zeros(len(trend), dtype=np.int64)
    for t in range(1, len(trend)):
        age[t] = age[t - 1] + 1 if trend[t] > 0 else 0
    return age


def _load_features(signals_path: str, data_root: str, interval: str = "15m",
                   research: dict | None = None):
    """Per-symbol channel arrays + research closes + cross-symbol breadth per ns.

    `research` lets a caller pass bars it has already loaded (the autoloop holds them
    for the whole run), avoiding a second full read per iteration."""
    z = np.load(signals_path)
    symbols = sorted({k.split("__")[0] for k in z.files})
    if research is None:
        research = Dataset(data_root=data_root, symbols=symbols, interval=interval).research()

    per_sym: dict[str, dict[str, np.ndarray]] = {}
    for s in symbols:
        d = {"ns": z[f"{s}__epoch_ns"].astype(np.int64)}
        for ch in ("prob", "trend", "vol", "mom", "hurst", "feargreed", "sweep"):
            d[ch] = z[f"{s}__{ch}"].astype(float)
        d["trend_age"] = _trend_age(d["trend"]).astype(float)
        bs = research.get(s) or []
        ns_close = {int(np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64")): b.close
                    for b in bs}
        d["close"] = np.array([ns_close.get(int(x), np.nan) for x in d["ns"].tolist()])
        per_sym[s] = d

    # Breadth: fraction of the universe in an uptrend at each timestamp, causal by
    # construction (trend itself is causal).
    up: dict[int, int] = {}
    present: dict[int, int] = {}
    for d in per_sym.values():
        for nsv, tr in zip(d["ns"].tolist(), d["trend"].tolist()):
            present[nsv] = present.get(nsv, 0) + 1
            if tr > 0:
                up[nsv] = up.get(nsv, 0) + 1
    breadth = {nsv: up.get(nsv, 0) / max(cnt, 1) for nsv, cnt in present.items()}
    for d in per_sym.values():
        d["breadth"] = np.array([breadth.get(int(x), 0.0) for x in d["ns"].tolist()])
    return per_sym


def _simulate_trades(per_sym: dict, enter: float, exit_: float, min_hold: int,
                     stop_loss: float, trail_stop: float) -> list[dict]:
    """Champion-rule trades per symbol on research closes, with features at entry."""
    trades: list[dict] = []
    for s, d in per_sym.items():
        close, prob, trend = d["close"], d["prob"], d["trend"]
        # The arrays span research + sealed bars, but research closes exist only
        # pre-lock — clamp the simulation to the last finite close so an unclosed
        # late-2025 trade exits at a real price instead of a NaN.
        fin = np.where(np.isfinite(close))[0]
        if len(fin) == 0:
            continue
        n = int(fin[-1]) + 1
        i = 0
        while i < n:
            if not (prob[i] >= enter and trend[i] > 0
                    and np.isfinite(close[i]) and close[i] > 0):
                i += 1
                continue
            e = i
            entry_px = close[e]
            peak = entry_px
            exit_j = None
            for j in range(e + 1, n):
                px = close[j]
                if not np.isfinite(px):
                    continue
                peak = max(peak, px)
                if stop_loss > 0 and px / entry_px - 1.0 <= -stop_loss:
                    exit_j = j
                    break
                if trail_stop > 0 and px <= peak * (1.0 - trail_stop):
                    exit_j = j
                    break
                if prob[j] <= exit_ and (j - e) >= min_hold:
                    exit_j = j
                    break
            if exit_j is None:
                exit_j = n - 1
            stamp = str(np.datetime64(int(d["ns"][e]), "ns"))
            trades.append({
                "net": float(close[exit_j] / entry_px - 1.0 - TOLL),
                "year": int(stamp[:4]), "month": int(stamp[5:7]),
                "x": [float(d[f][e]) for f in FEATURES],
            })
            i = exit_j + 1
    return trades


def build_sizing(signals_path: str, data_root: str, *,
                 enter: float, exit_: float, min_hold: int,
                 stop_loss: float, trail_stop: float,
                 seed: int = 7, lock_year: int = 2026,
                 research: dict | None = None) -> dict[str, dict[int, float]]:
    """The walk-forward size-multiplier overlay: `{symbol: {ns: mult}}`."""
    from sklearn.ensemble import HistGradientBoostingRegressor

    per_sym = _load_features(signals_path, data_root, research=research)
    trades = _simulate_trades(per_sym, enter, exit_, min_hold, stop_loss, trail_stop)
    X = np.array([t["x"] for t in trades], dtype=float)
    y_raw = np.array([t["net"] for t in trades], dtype=float)
    # Belt and braces: a non-finite outcome or feature must never reach the fit.
    ok = np.isfinite(y_raw) & np.isfinite(X).all(axis=1)
    X = X[ok]
    y = np.clip(y_raw[ok], -CLIP, CLIP)
    yrs = np.array([t["year"] for t in trades], dtype=int)[ok]
    mos = np.array([t["month"] for t in trades], dtype=int)[ok]

    # Per-bar feature matrix + bar years, per symbol.
    bar_year = {s: (d["ns"].astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970)
                for s, d in per_sym.items()}
    bar_X = {s: np.column_stack([d[f] for f in FEATURES]) for s, d in per_sym.items()}

    out: dict[str, dict[int, float]] = {s: {} for s in per_sym}

    def _score_year(model, train_pred, year_selector) -> None:
        for s, d in per_sym.items():
            m = year_selector(bar_year[s])
            if not m.any():
                continue
            mult = mults_from_preds(model.predict(bar_X[s][m]), train_pred)
            out[s].update(zip(d["ns"][m].tolist(), mult.tolist()))

    research_years = sorted({int(v) for v in yrs if v < lock_year})
    for year in research_years:
        tm = train_mask(yrs, mos, year)
        if tm.sum() < MIN_TRAIN_TRADES:
            continue                       # abstain: too little history to size honestly
        model = HistGradientBoostingRegressor(max_depth=3, max_iter=200,
                                              learning_rate=0.05, random_state=seed)
        model.fit(X[tm], y[tm])
        _score_year(model, model.predict(X[tm]), lambda by, _y=year: by == _y)

    # Sealed window (and anything after the last research year): research-only model.
    final_tm = yrs < lock_year
    if final_tm.sum() >= MIN_TRAIN_TRADES:
        model = HistGradientBoostingRegressor(max_depth=3, max_iter=200,
                                              learning_rate=0.05, random_state=seed)
        model.fit(X[final_tm], y[final_tm])
        _score_year(model, model.predict(X[final_tm]), lambda by: by >= lock_year)
    return out


def write_sizing(overlay: dict[str, dict[int, float]], out_path: str) -> None:
    """Write the overlay in the `load_overlay` format (`{sym}__size_ns`, `{sym}__size`)."""
    payload: dict[str, np.ndarray] = {}
    for sym, series in overlay.items():
        if not series:
            continue
        ns = np.array(sorted(series), dtype=np.int64)
        payload[f"{sym}__size_ns"] = ns
        payload[f"{sym}__size"] = np.array([series[int(v)] for v in ns], dtype=np.float32)
    np.savez(out_path, **payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signals", default=str(_workspace("system06") / "signals.npz"))
    parser.add_argument("--data-root", default="trading-system/backtester/data")
    parser.add_argument("--best", default=str(_workspace("system06") / "best.json"))
    parser.add_argument("--out", default=str(_workspace("system06") / "moneymodel.npz"))
    args = parser.parse_args()
    best = json.load(open(args.best, encoding="utf-8"))
    band, risk = best["band"], best["risk"]
    overlay = build_sizing(
        args.signals, args.data_root,
        enter=float(band["enter"]), exit_=float(band["exit_"]),
        min_hold=int(band["min_hold"]),
        stop_loss=float(risk.get("stop_loss", 0.0)),
        trail_stop=float(risk.get("trail_stop", 0.0)))
    write_sizing(overlay, args.out)
    bars = sum(len(v) for v in overlay.values())
    print(f"sizing overlay: {sum(1 for v in overlay.values() if v)} symbols, "
          f"{bars:,} scored bars -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
