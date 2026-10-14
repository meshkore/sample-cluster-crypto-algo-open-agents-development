"""Challengers: simple strategies the main line must keep beating (operator, 2026-10-14).

*"Never stop questioning whether this is the best idea or approach to earn as much money as
possible."* Each day the review books a handful of plain long-only strategies on the same
14 coins, the same candles and the same cost (`region.ROUND_TRIP`, half per side) as the
main line, and sets them beside the releases.

Booking: 4-hour closes resampled from the 15m candle cache (no World). Decisions on the UTC
day's last 4h close, filled at the NEXT bar's close. Each calendar year is a fresh account
that starts in cash and is liquidated at the last bar (both sides' costs charged); 2026 runs
to the latest bar. Judged like the search: years 2022-2025, worst year, CAGR, max DD
(cap 25%), Q = return^2 / max DD. 2020-2021 are shown; 2026 is reported, never used.

Caveat: the universe is today's 14 coins (survivorship), as it is for the main line.

    python -m system010_conditioned_rl.challengers        # writes rnd/challengers.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "research/system10"
RESULT = OUT / "rnd/challengers.json"
DATA = REPO / "trading-system/backtester/data"
UNIVERSE = REPO / "research/system06/universe.json"

try:
    from .region import ROUND_TRIP
except Exception:  # noqa: BLE001 - the project invariant, if region cannot be imported
    ROUND_TRIP = 0.003
HALF = ROUND_TRIP / 2
BAR_NS = 4 * 3600 * 10**9
PER_DAY = 6
FROM = "2019-01-01"               # warm-up for 200-day averages before 2020
YEARS = (2020, 2021, 2022, 2023, 2024, 2025)
TEST_YEARS = (2022, 2023, 2024, 2025)
FORWARD = 2026
DD_CAP = 0.25
DD_FLOOR = 0.02
VOL_TARGET = 0.50                  # annualised, for the vol-targeted trend


# ---------------------------------------------------------------------------- data

def _latest_csv(directory: Path) -> Path | None:
    from .health import _latest_csv as latest
    return latest(directory)


def load_4h(symbols: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """(grid ns [T], close [T, n]) of 4h closes from FROM to the latest bar; NaN before listing."""
    import pandas as pd
    t0 = np.datetime64(FROM, "ns").astype(np.int64)
    series = []
    for s in symbols:
        parts = []
        for phase in ("research", "forward"):
            f = _latest_csv(DATA / f"{phase}/processed/binance" / s / "15m")
            if f is None:
                continue
            df = pd.read_csv(f, usecols=["timestamp", "close"])
            ns = pd.DatetimeIndex(pd.to_datetime(df["timestamp"], utc=True)).as_unit("ns").asi8
            parts.append((ns, df["close"].to_numpy(dtype=float)))
        if not parts:
            series.append(None)
            continue
        ns = np.concatenate([p[0] for p in parts])
        c = np.concatenate([p[1] for p in parts])
        ns, first = np.unique(ns, return_index=True)    # research wins on any overlap
        c = c[first]
        keep = (ns >= t0) & np.isfinite(c) & (c > 0)
        series.append((ns[keep], c[keep]))
    hi = max(int(x[0][-1]) for x in series if x is not None and len(x[0]))
    grid = np.arange(t0 // BAR_NS, hi // BAR_NS + 1, dtype=np.int64) * BAR_NS
    close = np.full((len(grid), len(symbols)), np.nan)
    for j, x in enumerate(series):
        if x is None or not len(x[0]):
            continue
        b = (x[0] - grid[0]) // BAR_NS
        last = np.r_[b[1:] != b[:-1], True]               # the bucket's last 15m close
        close[b[last], j] = x[1][last]
        col = close[:, j]                                 # carry across gaps, never before listing
        ok = np.isfinite(col)
        idx = np.where(ok, np.arange(len(col)), 0)
        np.maximum.accumulate(idx, out=idx)
        filled = col[idx]
        filled[: np.argmax(ok)] = np.nan
        close[:, j] = filled
    return grid, close


# ---------------------------------------------------------------------------- book

def book(px: np.ndarray, target: np.ndarray, rebal: np.ndarray, lo: int, hi: int,
         eps: float = 0.01) -> dict:
    """Fresh account on bars lo..hi-1: the target decided at bar k-1 is filled at bar k's close
    when rebal[k-1] (and always at lo). Costs HALF per side on traded value; liquidated at hi-1."""
    n = px.shape[1]
    cash, units = 1.0, np.zeros(n)
    eq = np.empty(hi - lo)
    trades = 0
    for k in range(lo, hi):
        p = px[k]
        pz = np.nan_to_num(p)
        if k == lo or rebal[k - 1]:
            w = np.where(np.isfinite(p), target[k - 1] if k > 0 else 0.0, 0.0)
            val = units * pz
            e = cash + val.sum()
            if k == lo or np.abs(w - val / e).max() > eps:
                e2 = e
                for _ in range(4):                        # equity after this rebalance's costs
                    e2 = e - HALF * np.abs(w * e2 - val).sum()
                trades += int((np.abs(w * e2 - val) > 1e-12).sum())
                units = np.divide(w * e2, pz, out=np.zeros(n), where=pz > 0)
                cash = e2 - (w * e2).sum()
        eq[k - lo] = cash + (units * pz).sum()
    eq[-1] = cash + (units * np.nan_to_num(px[hi - 1])).sum() * (1 - HALF)
    peak = np.maximum.accumulate(np.r_[1.0, eq])
    dd = float((1 - np.r_[1.0, eq] / peak).max())
    ret = float(eq[-1] - 1)
    return {"return": round(ret, 4), "max_dd": round(dd, 4), "q": round(_q(ret, dd), 4), "trades": trades}


def _q(ret: float, dd: float) -> float:
    return (1.0 if ret >= 0 else -1.0) * ret * ret / max(dd, DD_FLOOR)


# ---------------------------------------------------------------------------- strategies

def _ma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    c = np.cumsum(np.r_[0.0, np.nan_to_num(x)])
    good = np.cumsum(np.r_[0, np.isfinite(x).astype(int)])
    s, g = c[n:] - c[:-n], good[n:] - good[:-n]
    out[n - 1:] = np.where(g == n, s / n, np.nan)
    return out


def _ffill_rows(a: np.ndarray, rows: np.ndarray) -> np.ndarray:
    """a[rows] carried forward over the rows between them (rows sorted)."""
    idx = np.where(rows, np.arange(len(a)), 0)
    np.maximum.accumulate(idx, out=idx)
    return a[idx]


def strategies(grid: np.ndarray, close: np.ndarray) -> dict:
    """name -> (target [T, n], rebal [T] bool, eps, description). Column 0 is BTC."""
    T, n = close.shape
    day = grid // (86400 * 10**9)
    eod = np.r_[day[1:] != day[:-1], True]                 # the UTC day's last 4h bar
    D = np.flatnonzero(eod)
    P = close[D]                                           # daily closes [d, n]
    dates = grid[D].astype("datetime64[ns]").astype("datetime64[D]")
    month = dates.astype("datetime64[M]")
    month_end = np.r_[month[1:] != month[:-1], True]
    week_end = ((dates.astype(np.int64) + 3) % 7) == 6      # Sunday (1970-01-01 was a Thursday)
    btc = P[:, 0]
    above = {m: np.nan_to_num(btc - _ma(btc, m), nan=-1.0) > 0 for m in (50, 100, 200)}
    cross = np.nan_to_num(_ma(btc, 50) - _ma(btc, 200), nan=-1.0) > 0
    avail = np.isfinite(P)
    ew = avail / np.maximum(avail.sum(1, keepdims=True), 1)
    one_btc = np.zeros_like(P)
    one_btc[:, 0] = 1.0

    def expand(tgt_d, reb_d, eps, text):
        tgt = np.zeros((T, n))
        tgt[D] = tgt_d
        tgt = _ffill_rows(tgt, eod)
        reb = np.zeros(T, dtype=bool)
        reb[D] = reb_d
        return tgt, reb, eps, text

    def flips(g):
        return np.r_[False, g[1:] != g[:-1]]

    out = {
        "btc_hold": expand(one_btc, np.zeros(len(D), bool), 1.0, "BTC buy & hold"),
        "ew_hold": expand(ew, month_end, 0.01, "equal-weight 14 coins, monthly rebalance"),
    }
    for m in (50, 100, 200):
        out[f"btc_ma{m}"] = expand(one_btc * above[m][:, None], np.ones(len(D), bool), 0.01,
                                   f"BTC when above its {m}-day average, else cash")
    out["btc_cross50_200"] = expand(one_btc * cross[:, None], np.ones(len(D), bool), 0.01,
                                    "BTC when its 50-day average is above the 200-day, else cash")
    g = above[100]
    out["ew_ma100"] = expand(ew * g[:, None], month_end | flips(g), 0.01,
                             "equal-weight 14 coins when BTC is above its 100-day average")
    for look in (30, 60):
        mom = np.full_like(P, np.nan)
        mom[look:] = P[look:] / P[:-look] - 1
        for k in (3, 5):
            sel = np.zeros_like(P)
            for d in np.flatnonzero(week_end):
                ok = np.flatnonzero(np.isfinite(mom[d]))
                if len(ok):
                    top = ok[np.argsort(-mom[d, ok])[:k]]
                    sel[d, top] = 1.0 / k
            sel = _ffill_rows(sel, week_end)
            out[f"mom{k}_{look}d"] = expand(sel * g[:, None], week_end | flips(g), 0.01,
                                            f"top {k} by {look}-day return, weekly, when BTC > 100-day avg")
    lr = np.diff(np.log(btc), prepend=np.nan)
    m1, m2 = _ma(lr, 30), _ma(lr * lr, 30)
    vol = np.sqrt(np.maximum(m2 - m1 * m1, 0) * 365)
    w = np.clip(np.nan_to_num(VOL_TARGET / np.maximum(vol, 1e-6), nan=0.0), 0, 1) * g
    out["btc_ma100_vt"] = expand(one_btc * w[:, None], week_end | flips(g), 0.05,
                                 f"BTC above 100-day avg, sized to {VOL_TARGET:.0%} annual vol, weekly")
    return out


# ---------------------------------------------------------------------------- main line

def _rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for x in path.read_text(encoding="utf-8").splitlines():
        if x.strip():
            try:
                out.append(json.loads(x))
            except ValueError:
                pass
    return out


def release_numbers(n: int | None = None) -> dict | None:
    """A release's record as published (2022-2025), its 2026 reading from the evaluator's
    timeline (latest row for that release id), and 2020-2021 from the health study if it
    booked the same release."""
    files = sorted((OUT / "releases").glob("release_*.json"))
    if not files:
        return None
    path = files[-1] if n is None else OUT / "releases" / f"release_{n:04d}.json"
    if not path.is_file():
        return None
    r = json.loads(path.read_text(encoding="utf-8"))
    years = {str(y): {k: v.get(k) for k in ("return", "max_dd", "q")} for y, v in r["years"].items()}
    hs = OUT / "rnd/health_study.json"
    cfg_path = OUT / "paper/config.json"
    try:
        pinned = json.loads(cfg_path.read_text(encoding="utf-8")).get("release_id") if cfg_path.is_file() else None
        if pinned == r["id"] and hs.is_file():
            base = json.loads(hs.read_text(encoding="utf-8"))["per_year"]["baseline"]
            for y in ("2020", "2021"):
                if y in base and y not in years:
                    years[y] = {"return": base[y]["return"], "max_dd": base[y]["max_dd"],
                                "q": round(_q(base[y]["return"], base[y]["max_dd"]), 4)}
    except (OSError, ValueError, KeyError):
        pass
    fwd = [x["forward_2026"] for x in _rows(OUT / "rnd/training_timeline.jsonl")
           if x.get("champion") == r["id"] and isinstance(x.get("forward_2026"), dict)
           and x["forward_2026"].get("return") is not None and x.get("at", "") >= "2026-10-10"]
    return {"release": r["n"], "id": r["id"], "label": r.get("label"),
            "worst_year": r["worst_year"], "cagr": r["cagr"],
            "max_dd": round(max(v["max_dd"] for y, v in years.items() if int(y) in TEST_YEARS), 4),
            "score": r.get("score"), "years": dict(sorted(years.items())),
            "forward_2026": ({k: fwd[-1].get(k) for k in ("return", "max_dd", "q")} if fwd else None)}


# ---------------------------------------------------------------------------- run

def summary(years: dict) -> dict:
    rets = [years[str(y)]["return"] for y in TEST_YEARS]
    worst = min(rets)
    cagr = float(np.prod([1 + x for x in rets]) ** (1 / len(rets)) - 1)
    all_r = [years[str(y)]["return"] for y in YEARS]
    return {"worst_year": round(worst, 4), "cagr": round(cagr, 4),
            "max_dd": round(max(years[str(y)]["max_dd"] for y in TEST_YEARS), 4),
            "worst_q": round(min(years[str(y)]["q"] for y in TEST_YEARS), 4),
            "score": round(worst + 0.10 * cagr, 4),
            "cagr_2020_2025": round(float(np.prod([1 + x for x in all_r]) ** (1 / len(all_r)) - 1), 4),
            "worst_2020_2025": round(min(all_r), 4)}


def verdict(ch: dict, main: dict) -> dict:
    v = {"worst_year": ch["worst_year"] > main["worst_year"], "cagr": ch["cagr"] > main["cagr"],
         "max_dd": ch["max_dd"] <= main["max_dd"]}
    v["all_three"] = all(v.values())
    v["alert"] = bool(v["worst_year"] and v["cagr"] and ch["max_dd"] <= DD_CAP)
    f, mf = ch.get("forward_2026"), main.get("forward_2026")
    v["forward_2026_better"] = (f["return"] > mf["return"]) if f and mf else None
    return v


def run(out: Path = RESULT, symbols: list[str] | None = None) -> dict:
    t0 = time.time()
    syms = symbols or json.loads(UNIVERSE.read_text(encoding="utf-8"))["symbols"]
    if syms[0] != "BTCUSDT":
        syms = ["BTCUSDT"] + [s for s in syms if s != "BTCUSDT"]
    grid, close = load_4h(syms)
    yr = grid.astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970
    res: dict = {}
    for name, (tgt, reb, eps, text) in strategies(grid, close).items():
        years = {}
        for y in YEARS + (FORWARD,):
            idx = np.flatnonzero(yr == y)
            if len(idx) > 1:
                years[str(y)] = book(close, tgt, reb, int(idx[0]), int(idx[-1]) + 1, eps)
        row = {"description": text, "years": {k: v for k, v in years.items() if k != str(FORWARD)}}
        if all(str(y) in years for y in YEARS):
            row.update(summary(years))
        row["forward_2026"] = years.get(str(FORWARD))
        res[name] = row
    newest = release_numbers()
    pinned_n = None
    cfg = OUT / "paper/config.json"
    if cfg.is_file():
        try:
            pinned_n = json.loads(cfg.read_text(encoding="utf-8")).get("release")
        except ValueError:
            pass
    pinned = release_numbers(pinned_n) if pinned_n and newest and pinned_n != newest["release"] else None
    ref = newest
    verdicts = {k: verdict(v, ref) for k, v in res.items() if ref and "cagr" in v}
    beat = [k for k, v in verdicts.items() if v["alert"]]
    last_bar = str(grid[-1].astype("datetime64[ns]"))[:16]
    ranked = [k for k in res if "cagr" in res[k]]
    capped = [k for k in ranked if res[k]["max_dd"] <= DD_CAP]
    key = lambda k: (res[k]["score"], res[k]["worst_q"])  # noqa: E731 - the search's own ranking
    best = max(capped or ranked, key=key, default=None)
    doc = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "last_bar": last_bar,
           "round_trip": ROUND_TRIP, "bars": "4h from 15m", "test_years": list(TEST_YEARS),
           "dd_cap": DD_CAP, "symbols": syms,
           "main_line": {"newest": newest, "pinned": pinned or newest},
           "challengers": res, "verdict": verdicts, "alerts": beat,
           "best": best, "best_within_dd_cap": bool(capped),
           "seconds": round(time.time() - t0, 1)}
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    tmp.replace(out)
    return doc


def table(doc: dict) -> str:
    ys = [str(y) for y in YEARS] + ["2026"]
    head = f"{'':18}" + "".join(f"{y:>13}" for y in ys) + f"{'worst22-25':>12}{'CAGR22-25':>11}{'maxDD':>7}"
    out = [head]

    def line(name, years, fwd, s):
        cells = []
        for y in ys:
            v = fwd if y == "2026" else years.get(y)
            cells.append(f"{v['return']:+7.1%}/{v['max_dd']:4.0%}" if v else f"{'-':>13}")
        out.append(f"{name:18}" + "".join(f"{c:>13}" for c in cells)
                   + (f"{s['worst_year']:+12.1%}{s['cagr']:+11.1%}{s['max_dd']:7.0%}" if "cagr" in s else ""))

    m = doc["main_line"]["newest"]
    if m:
        line(f"release {m['release']}", m["years"], m["forward_2026"], m)
    for k, v in doc["challengers"].items():
        line(k, v["years"], v["forward_2026"], v)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="S10 challengers: simple strategies vs the main line")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    doc = run()
    if not args.quiet:
        print(table(doc))
        print(f"alerts: {doc['alerts'] or 'none'}; best challenger: {doc['best']}; {doc['seconds']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
