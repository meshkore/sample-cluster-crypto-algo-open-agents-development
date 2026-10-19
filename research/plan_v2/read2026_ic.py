"""One registered reading of sealed 2026 (operator go "all of it", 2026-10-19): does the phase 3
cross-sectional signal survive in 2026? Signal-level only - no configuration is chosen with it.

Models are the phase 3 pipeline's, trained on every member row of 2020-2025 whose label ends before
2026 (fit_predict with N = 2026), both seed sets, every timeframe / horizon / model. They predict the
2026 PIT list (top 14 by turnover on 31 Dec 2025). Bars stop at the prospective lock (2026-10-19
00:00 UTC), so the prospective window stays unread.
Measured per month of 2026: Spearman IC of prediction vs realised net return (the phase 3 target) and vs the GROSS forward
return (the cost-free check, ic_check.py),
and the gross spread of the top 3 minus the bottom 3 by prediction over the horizon.
Logged to read2026_results.json and READINGS.md.

    python research/plan_v2/read2026_ic.py
"""

from __future__ import annotations

import json
import time
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

import phase3_select as P3

HERE = Path(__file__).resolve().parent
OUT = HERE / "read2026_results.json"
CUT = np.datetime64("2026-10-19T00:00:00", "ns").astype("int64")


def load_sealed(lists: dict) -> dict:
    f = P3.CACHE / "bars_2026.pkl"
    if f.exists():
        return pd.read_pickle(f)
    from quantlab_catalog.candles import candles
    coins = sorted({s for v in lists.values() for s in v})
    out = {"4h": {}, "1d": {}}
    for s in coins:
        bars = candles([s], include_sealed=True).get(s) or []
        df = pd.DataFrame({"ns": [np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64") for b in bars],
                           "open": [b.open for b in bars], "high": [b.high for b in bars], "low": [b.low for b in bars],
                           "close": [b.close for b in bars], "usd": [b.volume * b.close for b in bars],
                           "tk": [(b.taker_buy_volume or 0.0) * b.close for b in bars]})
        df = df[df["ns"] < CUT]
        for tf, step in (("4h", P3.H4), ("1d", P3.D1)):
            g = df.groupby(df["ns"] // step * step + step)
            r = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                              "close": g["close"].last(), "usd": g["usd"].sum(), "tk": g["tk"].sum()})
            r["taker"] = r["tk"] / r["usd"].replace(0, np.nan)
            out[tf][s] = r.drop(columns="tk")
        print(f"  {s}: {len(df):,} 15m bars", flush=True)
    pd.to_pickle(out, f)
    return out


def panel(bars: dict, tf: str, lists: dict) -> dict:
    coins = sorted(bars[tf])
    grid = np.unique(np.concatenate([bars[tf][s].index.values for s in coins]))
    grid = grid[(P3.year_of(grid) >= 2020) & (grid <= CUT)]
    cols = {c: np.column_stack([bars[tf][s][c].reindex(grid).values for s in coins]).astype(float)
            for c in ("open", "high", "low", "close", "usd", "taker")}
    yr = P3.year_of(grid)
    member = np.zeros((len(grid), len(coins)), dtype=bool)
    for y, v in lists.items():
        for j, s in enumerate(coins):
            if s in v:
                member[yr == y, j] = True
    member &= np.isfinite(cols["close"])
    return {"grid": grid, "coins": coins, "year": yr, "member": member, **cols}


def main() -> int:
    t0 = time.time()
    from system010_conditioned_rl import pit
    from system010_conditioned_rl import universe_pit as U
    lists = {int(y): list(v) for y, v in pit.union_lists(pit.CAP, pit.UNION_YEARS).items()}
    lists[2026] = list(U.load(2026, 14))
    bars = load_sealed(lists)
    res = {"cut": "2026-10-19T00:00Z", "list_2026": lists[2026], "cells": {}}
    for tf in ("4h", "1d"):
        P = panel(bars, tf, lists)
        imp = P3.impact(P, tf)
        X, _ = P3.features(P, tf)
        n = P3.BARS_PER_DAY[tf]
        rows = np.flatnonzero(P["year"] == 2026)
        month = P["grid"][rows].astype("datetime64[ns]").astype("datetime64[M]").astype(str)
        for h, model, ss in product((1, 3, 7), ("ridge", "gbm"), P3.SEED_SETS):
            y, end = P3.target(P, tf, h, imp)
            pr = P3.fit_predict(X, y, end, P, model, P3.SEED_SETS[ss], 2026)
            c = P["close"]
            fwd = np.full_like(c, np.nan)
            H = h * n
            fwd[: len(c) - 1 - H] = c[1 + H:] / c[1: len(c) - H] - 1
            by_m: dict = {}
            for i, t in enumerate(rows[::n]):
                a, b = pr[i * n], y[t]
                ok = np.isfinite(a) & np.isfinite(b) & P["member"][t]
                if ok.sum() < 8:
                    continue
                ic = pd.Series(a[ok]).corr(pd.Series(b[ok]), method="spearman")
                okg = ok & np.isfinite(fwd[t])
                icg = pd.Series(a[okg]).corr(pd.Series(fwd[t][okg]), method="spearman") if okg.sum() >= 8 else np.nan
                order = np.argsort(-np.where(ok, a, -np.inf))
                top, bot = order[:3], np.argsort(np.where(ok, a, np.inf))[:3]
                spread = float(np.nanmean(fwd[t, top]) - np.nanmean(fwd[t, bot]))
                by_m.setdefault(month[i * n], []).append((ic, spread, icg))
            cell = {}
            allv = [v for m in by_m.values() for v in m]
            for m, v in sorted(by_m.items()):
                ics = np.array([x[0] for x in v])
                cell[m] = {"ic": round(float(np.nanmean(ics)), 4), "spread_top3_bot3": round(float(np.nanmean([x[1] for x in v])), 4)}
            ics = np.array([x[0] for x in allv])
            cell["all"] = {"ic": round(float(np.nanmean(ics)), 4),
                           "ic_t": round(float(np.nanmean(ics) / (np.nanstd(ics) + 1e-12) * np.sqrt(np.isfinite(ics).sum() / max(1, h))), 2),
                           "days": int(np.isfinite(ics).sum()),
                           "spread_top3_bot3": round(float(np.nanmean([x[1] for x in allv])), 4),
                           "ic_gross": round(float(np.nanmean([x[2] for x in allv])), 4),
                           "ic_gross_t": round(float(np.nanmean([x[2] for x in allv]) / (np.nanstd([x[2] for x in allv]) + 1e-12)
                                                     * np.sqrt(np.isfinite([x[2] for x in allv]).sum() / max(1, h))), 2)}
            res["cells"][f"{tf} H={h}d {model} {ss}"] = cell
            print(f"[{time.time() - t0:.0f}s] {tf} H={h}d {model} {ss}: IC {cell['all']['ic']} t {cell['all']['ic_t']} "
                  f"spread {cell['all']['spread_top3_bot3']} | GROSS IC {cell['all']['ic_gross']} t {cell['all']['ic_gross_t']}", flush=True)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
