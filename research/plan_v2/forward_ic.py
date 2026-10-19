"""Forward tracker of the one signal that survived sealed 2026 (READINGS.md #1): 4h bars, 1-day
horizon, ridge and GBM, both seed sets, models frozen on 2020-2025 (the phase 3 fit, N = 2026).

Every run (Windows task "plan-v2-forward-ic", every 4 h):
  1. fits the frozen models on the research panel (cache/bars.pkl, <= 2025; deterministic seeds)
  2. loads live candles of the 2026 PIT list from 2025-07-01 (feature history) to now
  3. predicts every 4h bar from the prospective lock (2026-10-19 00:00 UTC) on
  4. scores each bar whose 1-day gross forward return is complete: Spearman IC, top-3 minus
     bottom-3 gross spread
  5. writes forward/forward_ic.json (per bar) and forward/FORWARD.md (summary with a t-stat)
It never chooses, tunes or trades anything; the prospective window is read only here.

    python research/plan_v2/forward_ic.py
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

import phase3_select as P3

HERE = Path(__file__).resolve().parent
FWD = HERE / "forward"
LOCK = np.datetime64("2026-10-19T00:00:00", "ns").astype("int64")
HIST_FROM = np.datetime64("2025-07-01T00:00:00", "ns").astype("int64")
TF, H_DAYS = "4h", 1


def live_bars(coins: list[str]) -> dict:
    from quantlab_catalog.candles import candles
    out = {TF: {}}
    for s in coins:
        bars = candles([s], include_sealed=True).get(s) or []
        df = pd.DataFrame({"ns": [np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64") for b in bars],
                           "open": [b.open for b in bars], "high": [b.high for b in bars], "low": [b.low for b in bars],
                           "close": [b.close for b in bars], "usd": [b.volume * b.close for b in bars],
                           "tk": [(b.taker_buy_volume or 0.0) * b.close for b in bars]})
        df = df[df["ns"] >= HIST_FROM]
        g = df.groupby(df["ns"] // P3.H4 * P3.H4 + P3.H4)
        r = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                          "close": g["close"].last(), "usd": g["usd"].sum(), "tk": g["tk"].sum(),
                          "n15": g["close"].count()})
        r = r[r["n15"] == 16]                       # complete 4h bars only
        r["taker"] = r["tk"] / r["usd"].replace(0, np.nan)
        out[TF][s] = r.drop(columns=["tk", "n15"])
    return out


def live_panel(bars: dict, coins: list[str]) -> dict:
    grid = np.unique(np.concatenate([bars[TF][s].index.values for s in coins]))
    cols = {c: np.column_stack([bars[TF][s][c].reindex(grid).values for s in coins]).astype(float)
            for c in ("open", "high", "low", "close", "usd", "taker")}
    member = np.isfinite(cols["close"])
    return {"grid": grid, "coins": coins, "year": P3.year_of(grid), "member": member, **cols}


def main() -> int:
    t0 = time.time()
    from system010_conditioned_rl import pit
    from system010_conditioned_rl import universe_pit as U
    FWD.mkdir(exist_ok=True)
    lists = {int(y): list(v) for y, v in pit.union_lists(pit.CAP, pit.UNION_YEARS).items()}
    coins26 = sorted(U.load(2026, 14))
    # 1. training panel (research bars) and the frozen fits
    bars, _ = P3.load_bars()
    Ptr = P3.panel(bars, TF, lists)
    imp = P3.impact(Ptr, TF)
    Xtr, names = P3.features(Ptr, TF)
    y, end = P3.target(Ptr, TF, H_DAYS, imp)
    F = Xtr.shape[2]
    tr = (Ptr["year"] <= 2025) & (end < len(Ptr["grid"]) - 1)
    Xt, yt = Xtr[tr].reshape(-1, F), y[tr].reshape(-1)
    ok = np.isfinite(Xt).all(axis=1) & np.isfinite(yt)
    Xt, yt = Xt[ok], yt[ok]
    mu, sd = Xt.mean(axis=0), Xt.std(axis=0) + 1e-9
    models = {}
    for ss, seeds in P3.SEED_SETS.items():
        for kind in ("ridge", "gbm"):
            fits = []
            for seed in seeds:
                pick = np.random.default_rng(seed).random(len(yt)) < 0.8
                if kind == "ridge":
                    fits.append(Ridge(alpha=10.0).fit((Xt[pick] - mu) / sd, yt[pick]))
                else:
                    fits.append(HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                                              min_samples_leaf=200, random_state=seed).fit(Xt[pick], yt[pick]))
            models[(kind, ss)] = fits
    # 2-3. live panel, predictions from the lock on
    Pl = live_panel(live_bars(coins26), coins26)
    Xl, _ = P3.features(Pl, TF)
    c = Pl["close"]
    H = H_DAYS * P3.BARS_PER_DAY[TF]
    fwd = np.full_like(c, np.nan)
    fwd[: len(c) - 1 - H] = c[1 + H:] / c[1: len(c) - H] - 1
    rows = np.flatnonzero(Pl["grid"] > LOCK)
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "lock": "2026-10-19T00:00Z",
           "coins": coins26, "signal": f"{TF} bars, {H_DAYS}-day horizon", "cells": {}}
    for (kind, ss), fits in models.items():
        per_bar = []
        for t in rows:
            x = Xl[t]
            okx = np.isfinite(x).all(axis=1) & Pl["member"][t]
            if okx.sum() < 8:
                continue
            p = np.full(len(coins26), np.nan)
            xx = x[okx]
            p[okx] = np.mean([m.predict((xx - mu) / sd) if kind == "ridge" else m.predict(xx) for m in fits], axis=0)
            row = {"t": str(Pl["grid"][t].astype("datetime64[ns]"))[:16], "pred_top3": [coins26[j] for j in np.argsort(-np.nan_to_num(p, nan=-9))[:3]]}
            okf = okx & np.isfinite(fwd[t])
            if okf.sum() >= 8:
                row["ic_gross"] = round(float(pd.Series(p[okf]).corr(pd.Series(fwd[t][okf]), method="spearman")), 4)
                o = np.argsort(-np.where(okf, p, -np.inf))
                b = np.argsort(np.where(okf, p, np.inf))
                row["spread_top3_bot3"] = round(float(fwd[t][o[:3]].mean() - fwd[t][b[:3]].mean()), 5)
            per_bar.append(row)
        scored = [r["ic_gross"] for r in per_bar if "ic_gross" in r]
        daily = scored[:: P3.BARS_PER_DAY[TF]]
        out["cells"][f"{kind} {ss}"] = {
            "bars_predicted": len(per_bar), "bars_scored": len(scored),
            "mean_ic_gross": round(float(np.mean(scored)), 4) if scored else None,
            "t_daily_nonoverlap": round(float(np.mean(daily) / (np.std(daily, ddof=1) + 1e-12) * np.sqrt(len(daily))), 2) if len(daily) > 2 else None,
            "mean_spread_top3_bot3": round(float(np.mean([r["spread_top3_bot3"] for r in per_bar if "spread_top3_bot3" in r])), 5) if scored else None,
            "per_bar": per_bar}
    (FWD / "forward_ic.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    lines = ["# Forward tracker: the 4h / 1-day signal on the prospective window", "",
             f"Updated {out['generated']}. Models frozen on 2020-2025; window from 2026-10-19 00:00 UTC; the 2026 PIT list.",
             "Sealed-2026 reference (READINGS.md #1): gross IC 0.049-0.059, t 2.4-2.8. A t is reported once 30+ days exist.", "",
             "| model, seed set | bars predicted | bars scored | mean gross IC | t (daily, non-overlapping) | top-3 minus bottom-3, gross per day |",
             "|---|---|---|---|---|---|"]
    for k, v in out["cells"].items():
        t_ = v["t_daily_nonoverlap"] if v["bars_scored"] >= 30 * 6 else "n < 30 days"
        lines.append(f"| {k} | {v['bars_predicted']} | {v['bars_scored']} | {v['mean_ic_gross']} | {t_} | {v['mean_spread_top3_bot3']} |")
    (FWD / "FORWARD.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[{time.time() - t0:.0f}s] " + "; ".join(f"{k}: {v['bars_scored']} scored, IC {v['mean_ic_gross']}" for k, v in out["cells"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
