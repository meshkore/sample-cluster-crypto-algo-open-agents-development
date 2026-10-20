"""Shadow paper book v2: the lab's paper candidate, frozen and traded on the prospective window.

Candidate (lab REPORT, paper gate, 2026-10-20): cap14-spot_long-xs-base-mlp - long only, Binance spot,
top-14 PIT list, ranking target, base features, MLP; mean nested Sharpe +0.64 over 100 seed pairs,
100% positive, median DD 40%. Pre-registered here, before any prospective bar is read:
  selection   its 36 inner configurations (4h/1d x 1/3/7 d x K 3/5/8) fitted walk-forward 2021-2025 on seed
              set s1; the 10 with the best p5 bootstrap Sharpe over 2021-2025 (no DD filter), bagged
  scale       exposure x 0.18 / the bag's 2021-2025 max DD (the plan's 18% budget)
  models      each chosen (timeframe, horizon) refitted on every member row <= 2025 (label-end embargo)
  book        $50,000 from the lock (2026-10-19 00:00 UTC), flat at the start; decide at a bar's close,
              fill at the next (4h grid), 0.225% + ADV impact per side, phase 4 risk layer, BTC > MA100 gate;
              the 2026 PIT list
Writes paper_v2/selection.json (once; frozen thereafter) and paper_v2/state.json (every run, from the
forward task). Never trades real money; plan phase 5 decides that from this book's months of results.

    python research/plan_v2/paper_v2.py
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

import lab_v2 as LV
import phase3_select as P3
import phase4_risk as P4R

HERE = Path(__file__).resolve().parent
OUT = HERE / "paper_v2"
SEL = OUT / "selection.json"
STATE = OUT / "state.json"
SPEC = dict(cap=14, venue="spot_long", target="xs", feats="base", family="mlp")
LOCK = np.datetime64("2026-10-19T00:00:00", "ns").astype("int64")
CAPITAL = 50_000.0
BAG = 10


def select() -> dict:
    """The frozen choice, made on research bars only (World(14) never loads 2026)."""
    w = LV.World(14)
    seeds = P3.SEED_SETS["s1"]
    rows = []
    for tf, h, k in product(LV.INNER["tf"], LV.INNER["h_days"], LV.INNER["k"]):
        cfg = dict(tf=tf, h_days=h, k=k, model="mlp")
        pr = w.preds(tf, h, "mlp", seeds, "xs", "base")
        Wx = LV.book(w, SPEC, cfg, pr)
        sim = LV.simulate(Wx, w.P4, w.imp["4h"], P3.HALF_COST, None)
        d = sim["daily"][np.isin(sim["dyear"], P3.TEST_YEARS)]
        rows.append((P3.boot_sharpe_p5(d), cfg, Wx))
    rows.sort(key=lambda r: -r[0])
    top = rows[:BAG]
    Wb = np.mean([r[2] for r in top], axis=0)
    sim = LV.simulate(Wb, w.P4, w.imp["4h"], P3.HALF_COST, None)
    d = sim["daily"][np.isin(sim["dyear"], P3.TEST_YEARS)]
    eq = np.cumprod(1 + d)
    dd = float((1 - eq / np.maximum.accumulate(eq)).max())
    sel = {"spec": SPEC, "made": datetime.now(timezone.utc).isoformat(timespec="seconds"), "seed_set": "s1",
           "configs": [{"cfg": c, "p5_sharpe": round(s, 3)} for s, c, _ in top],
           "backtest_2021_2025": P3.ci(d), "max_dd": round(dd, 4), "scale": round(min(1.0, 0.18 / dd), 4)}
    OUT.mkdir(exist_ok=True)
    SEL.write_text(json.dumps(sel, indent=1), encoding="utf-8")
    return sel


def live_world(cut_ns: int) -> dict:
    """Research history + live 2026 bars for the top-14 lists of 2020-2026, cut at `cut_ns`."""
    from system010_conditioned_rl import pit
    from system010_conditioned_rl import universe_pit as U
    from quantlab_catalog.candles import candles
    lists = {int(y): list(v) for y, v in pit.union_lists(14, pit.UNION_YEARS).items()}
    lists[2026] = list(U.load(2026, 14))
    coins = sorted({s for v in lists.values() for s in v})
    bars = {"4h": {}, "1d": {}}
    for s in coins:
        b = candles([s], include_sealed=True).get(s) or []
        df = pd.DataFrame({"ns": [np.datetime64(x.timestamp.replace(tzinfo=None), "ns").astype("int64") for x in b],
                           "open": [x.open for x in b], "high": [x.high for x in b], "low": [x.low for x in b],
                           "close": [x.close for x in b], "usd": [x.volume * x.close for x in b],
                           "tk": [(x.taker_buy_volume or 0.0) * x.close for x in b]})
        df = df[df["ns"] < cut_ns]
        for tf, step in (("4h", P3.H4), ("1d", P3.D1)):
            g = df.groupby(df["ns"] // step * step + step)
            r = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                              "close": g["close"].last(), "usd": g["usd"].sum(), "tk": g["tk"].sum(), "n": g["close"].count()})
            r = r[r["n"] == step // (15 * 60 * 10**9)]          # complete bars only
            r["taker"] = r["tk"] / r["usd"].replace(0, np.nan)
            bars[tf][s] = r.drop(columns=["tk", "n"])
    P = {}
    for tf in ("4h", "1d"):
        grid = np.unique(np.concatenate([bars[tf][s].index.values for s in coins]))
        grid = grid[P3.year_of(grid) >= 2020]
        cols = {c: np.column_stack([bars[tf][s][c].reindex(grid).values for s in coins]).astype(float)
                for c in ("open", "high", "low", "close", "usd", "taker")}
        yr = P3.year_of(grid)
        member = np.zeros((len(grid), len(coins)), dtype=bool)
        for y, v in lists.items():
            for j, s in enumerate(coins):
                if s in v:
                    member[yr == y, j] = True
        member &= np.isfinite(cols["close"])
        P[tf] = {"grid": grid, "coins": coins, "year": yr, "member": member, **cols}
    return P


def run() -> int:
    t0 = time.time()
    sel = json.loads(SEL.read_text(encoding="utf-8")) if SEL.exists() else select()
    now_ns = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "ns").astype("int64")
    P = live_world(now_ns)
    P4 = P["4h"]
    imp = {tf: P3.impact(P[tf], tf) for tf in P}
    sig, cov = P4R.daily_risk(P["1d"])
    day_of_bar = np.searchsorted(P["1d"]["grid"], P4["grid"], side="right") - 1
    seeds = P3.SEED_SETS["s1"]
    Ws = []
    preds_cache = {}
    for c in sel["configs"]:
        cfg = c["cfg"]
        tf, h = cfg["tf"], cfg["h_days"]
        if (tf, h) not in preds_cache:
            Pt = P[tf]
            X, _ = P3.features(Pt, tf)
            n = P3.BARS_PER_DAY[tf]
            cl = Pt["close"]
            H = h * n
            g = np.full_like(cl, np.nan)
            g[: len(cl) - 1 - H] = cl[1 + H:] / cl[1: len(cl) - H] - 1
            g = np.where(Pt["member"], g, np.nan)
            with np.errstate(invalid="ignore"):
                y = np.clip(g - np.nanmean(g, axis=1, keepdims=True), -0.5, 0.5)
            end = np.minimum(np.arange(len(cl)) + 1 + H, len(cl) - 1)
            pr = np.full_like(cl, np.nan)
            pr[Pt["year"] == 2026] = LV.fit_predict_mlp(X, y, end, Pt, seeds, 2026)
            preds_cache[(tf, h)] = pr
        Pt = P[tf]
        btc = pd.Series(Pt["close"][:, Pt["coins"].index("BTCUSDT")])
        gate = (btc > btc.rolling(100 * P3.BARS_PER_DAY[tf], min_periods=100 * P3.BARS_PER_DAY[tf]).mean()).values
        W = P3.decide(np.where(np.isfinite(preds_cache[(tf, h)]), preds_cache[(tf, h)] + 1.0, np.nan), Pt["member"],
                      cfg["k"], gate, hold=h * P3.BARS_PER_DAY[tf])
        Wx = P3.to_exec_4h(W, Pt["grid"], P4["grid"])
        Ws.append(P4R.risk_weights(Wx, P4, day_of_bar, sig, cov))
    Wb = np.mean(Ws, axis=0) * sel["scale"]
    live = P4["grid"] > LOCK
    Wb[~live] = 0.0
    c = P4["close"]
    R = np.zeros_like(c)
    R[:-1] = np.nan_to_num(c[1:] / c[:-1] - 1)
    Wb = np.where(np.isfinite(c), Wb, 0.0)
    dW = np.abs(np.diff(np.r_[np.zeros((1, Wb.shape[1])), Wb], axis=0))
    yi = np.clip(P4["year"] - 2020, 0, 6)
    cost = (dW * (P3.HALF_COST + imp["4h"][yi])).sum(axis=1)
    r = (Wb * R).sum(axis=1) - cost
    r[-1] = 0.0                                   # the last bar's return is not known yet
    idx = np.flatnonzero(live)
    eq = CAPITAL * np.cumprod(1 + r[idx]) if len(idx) else np.array([CAPITAL])
    peak = np.maximum.accumulate(eq) if len(eq) else eq
    last = Wb[-1]
    state = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "since": "2026-10-19T00:00Z",
             "candidate": LV.spec_id(SPEC), "capital": CAPITAL,
             "equity": round(float(eq[-1]), 2), "return_pct": round(float(eq[-1] / CAPITAL - 1), 5),
             "max_drawdown": round(float((1 - eq / peak).max()), 5) if len(eq) else 0.0,
             "exposure": round(float(last.sum()), 4), "turnover": round(float(dW[live].sum()), 3),
             "costs_usd": round(float((cost[idx] * CAPITAL).sum()), 2),
             "positions": [{"symbol": P4["coins"][j], "weight": round(float(last[j]), 4)} for j in np.flatnonzero(last > 1e-6)],
             "curve": [[str(P4["grid"][i].astype("datetime64[ns]"))[:16], round(float(e), 2)] for i, e in zip(idx, eq)],
             "last_bar": str(P4["grid"][-1].astype("datetime64[ns]"))[:16],
             "selection": {"configs": [x["cfg"] for x in sel["configs"]], "scale": sel["scale"],
                           "backtest_sharpe": sel["backtest_2021_2025"]["sharpe"], "backtest_max_dd": sel["max_dd"]}}
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    print(f"[{time.time() - t0:.0f}s] paper v2: equity {state['equity']:,.0f} ({state['return_pct']:+.2%}), "
          f"{len(state['positions'])} positions, exposure {state['exposure']:.0%}, bars {len(idx)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
