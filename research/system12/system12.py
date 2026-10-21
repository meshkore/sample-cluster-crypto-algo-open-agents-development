"""System 12 - the BTC regime is the core (operator go 2026-10-21, after Classics 11 showed that "equal-weight basket
while BTC > its 100-day average" earns almost what System 11 earns at equal risk: the coin-ranking net adds little).

Hypothesis: technical analysis applied to the WHOLE market (when to be in, how much) carries the edge; what to hold
inside the market is second order. So System 12 searches, exhaustively and walk-forward:

    regime     one BTC/market technical signal, or the mean (graded) or AND of two:
               BTC above its n-day average, an ensemble of averages, MA-ratio rules (Detzel 2021),
               time-series momentum, Donchian breakout state (Zarattini 2025), market breadth
    basket     what is held while the regime is on: BTC, BTC+ETH, equal weight of the members, inverse
               volatility, the 5 strongest coins (90-day), members above their own 50-day average, or
               System 11's model picks
    sizing     none or a volatility target on the basket (40 / 60 / 80% a year); exposure in steps of 25%
               so it does not trade every day

Honesty: rules are deterministic (no seeds). Point-in-time top-14 lists, delisted coins included; signals read at
the last daily close before each 4h decision; 0.225%/side + impact; each year from the same capital. Year N is
read with the configuration(s) chosen on 2019..N-1 only - both the single best and the average of the 20 best.
2026 is the forward test: chosen on 2019-2025, never used to choose.

    python research/system12/system12.py      -> research/system12/out/{results.json, REPORT.md, history.json}
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plan_v2"))
import bayes11 as B          # noqa: E402
import classics11 as K       # noqa: E402
import history_v2 as H       # noqa: E402
import rocket11 as R         # noqa: E402

OUT = HERE / "out"
CAP = 14
YEARS = tuple(range(2019, 2027))
FOLDS = tuple(range(2020, 2027))
FIRST = 2019
TOPK = 20
VOLT = (0.0, 0.4, 0.6, 0.8)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def progress(**k) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "progress.json").write_text(json.dumps({"at": now(), **k}), encoding="utf-8")


# ------------------------------------------------------------------ regime signals (daily, 0..1)

def signals(ctx: K.Ctx) -> dict[str, np.ndarray]:
    C, jb = ctx.C, ctx.jb
    btc = C[jb]
    sm = lambda n: btc.rolling(n, min_periods=n).mean()  # noqa: E731
    out = {}
    for n in (20, 50, 100, 150, 200):
        out[f"BTC>MA{n}"] = (btc > sm(n)).values.astype(float)
    out["BTC MA ensemble 20/50/100/200"] = np.mean([out[f"BTC>MA{n}"] for n in (20, 50, 100, 200)], axis=0)
    out["BTC MA-ratio rules (Detzel)"] = np.mean([(sm(s) > sm(l)).values for s in (5, 10, 20) for l in (50, 100, 200)], axis=0).astype(float)
    for n in (7, 14, 30, 60, 90, 180):
        out[f"BTC {n}d momentum"] = (btc / btc.shift(n) > 1).values.astype(float)
    for n in (20, 55, 100):
        out[f"BTC Donchian {n}d"] = K.donchian_state(ctx, n)[:, jb].astype(float)
    for n in (50, 100, 200):
        above = (C > C.rolling(n, min_periods=n).mean()).values & ctx.M
        share = above.sum(axis=1) / np.maximum(ctx.M.sum(axis=1), 1)
        out[f"breadth >{n}d avg"] = share
        out[f"breadth >{n}d avg > half"] = (share > 0.5).astype(float)
    for k in out:
        out[k] = np.nan_to_num(out[k])
    return out


def regimes(sig: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    out = dict(sig)
    for a, b in combinations(sorted(sig), 2):
        out[f"mean({a} | {b})"] = (sig[a] + sig[b]) / 2
        out[f"{a} AND {b}"] = np.minimum(sig[a], sig[b])
    return out


# ------------------------------------------------------------------ baskets (daily rows summing to 1, or 4h)

def baskets(ctx: K.Ctx, mlp4: np.ndarray) -> dict[str, np.ndarray]:
    C, M, jb, je = ctx.C, ctx.M, ctx.jb, ctx.je
    out = {"BTC": ctx.only(jb, 1.0), "BTC+ETH": ctx.only(jb, 0.5) + ctx.only(je, 0.5), "equal weight": ctx.ew()}
    vol = ctx.ewma_vol(30)
    iv = np.where(M & np.isfinite(vol) & (vol > 0), 1 / np.where(vol > 0, vol, 1), 0.0)
    out["inverse volatility"] = iv / np.maximum(iv.sum(axis=1, keepdims=True), 1e-12)
    out["5 strongest (90d)"] = top_n(ctx, (C / C.shift(90)).values, 5)
    tr = M & ctx.ma_above(50)
    out["members above own 50d avg"] = np.where(tr, 1.0, 0.0) / np.maximum(tr.sum(axis=1, keepdims=True), 1)
    out["System 11 model picks"] = mlp4                                  # 4h
    return out


def top_n(ctx: K.Ctx, X: np.ndarray, n: int) -> np.ndarray:
    D = np.zeros((ctx.nD, ctx.S))
    for k in range(ctx.nD):
        ok = ctx.M[k] & np.isfinite(X[k])
        j = np.where(ok)[0]
        if len(j):
            pick = j[np.argsort(X[k, j])[-n:]]
            D[k, pick] = 1.0 / len(pick)
    return D


class Engine:
    def __init__(self, w, ctx: K.Ctx, bk: dict, mlp4: np.ndarray):
        self.w, self.ctx, self.bk = w, ctx, bk
        self.dy = H.to_daily(w, np.zeros(len(w.P4["grid"])))[1]
        self.b4 = {k: (v if v.shape[0] != ctx.nD else ctx.to4h(v)) for k, v in bk.items()}
        R1 = np.nan_to_num(ctx.R.values)
        self.bret = {k: (np.nansum(v * R1, axis=1) if v.shape[0] == ctx.nD else None) for k, v in bk.items()}
        self.bret["System 11 model picks"] = self.bret["equal weight"]       # vol proxy for the model basket

    def exposure(self, reg: np.ndarray, basket: str, vt: float) -> np.ndarray:
        e = reg.copy()
        if vt:
            r = pd.Series(self.bret[basket])
            vol = r.rolling(30, min_periods=20).std().values * np.sqrt(365)
            e = e * np.clip(vt / np.where(np.isfinite(vol) & (vol > 0), vol, np.inf), 0, 1)
            e = np.where(np.isfinite(vol), e, 0.0)
        return np.floor(e * 4 + 1e-9) / 4                                  # steps of 25%

    def weights(self, reg: np.ndarray, basket: str, vt: float) -> np.ndarray:
        e = self.exposure(reg, basket, vt)
        e4 = e[np.clip(self.ctx.dk, 0, None)]
        e4[self.ctx.dk < 0] = 0.0
        W = self.b4[basket] * e4[:, None]
        return np.where(self.w.P4["member"] & np.isfinite(self.w.P4["close"]), W, 0.0)

    def daily(self, W: np.ndarray) -> np.ndarray:
        return self.ctx.run(W)[0]


def main() -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    progress(stage="loading the point-in-time data", done=0, total=1)
    cut = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "ns").astype("int64")
    w = H.world(CAP, int(cut))
    ctx = K.Ctx(w)
    T, S = w.P4["close"].shape
    z = np.load(R.CACHE / "base.npz")
    Wm = z["s2_W"].astype(float)                                          # the worse seed set of System 11
    Wm = np.r_[Wm, np.zeros((T - Wm.shape[0], S))]
    tot = Wm.sum(axis=1, keepdims=True)
    mlp4 = np.where(tot > 1e-9, Wm / np.maximum(tot, 1e-12), 0.0)
    early = w.P4["year"] < 2020                                           # no model picks before 2020: equal weight
    mlp4[early] = ctx.to4h(ctx.ew())[early]
    eng = Engine(w, ctx, baskets(ctx, mlp4), mlp4)
    regs = regimes(signals(ctx))
    keys = [(r, b, v) for r in regs for b in eng.b4 for v in VOLT]
    dy = eng.dy
    daily = np.zeros((len(keys), len(dy)), dtype=np.float32)
    for i, (r, b, v) in enumerate(keys):
        daily[i] = eng.daily(eng.weights(regs[r], b, v))
        if i % 200 == 0:
            progress(stage="testing every regime x basket x sizing", done=i, total=len(keys), minutes=round((time.time() - t0) / 60, 1))
    np.save(OUT / "daily.npy", daily)
    progress(stage="walk-forward selection", done=len(keys), total=len(keys))
    yrs = {i: B.yearly(daily[i].astype(float), dy, YEARS) for i in range(len(keys))}
    folds = {}
    for N in FOLDS:
        train = tuple(range(FIRST, N))
        sc = np.array([B.objective_value(daily[i].astype(float), dy, train)[0] for i in range(len(keys))])
        order = np.argsort(-sc)
        top = order[:TOPK]
        Wens = sum(eng.weights(regs[keys[i][0]], keys[i][1], keys[i][2]) for i in top) / len(top)
        d_ens = eng.daily(Wens)
        folds[N] = {"train": f"{FIRST}-{N - 1}", "best": {"cfg": list(keys[order[0]]), "score": round(float(sc[order[0]]), 4),
                                                         "ret": round(yrs[order[0]][N], 4)},
                    "ensemble": {"ret": round(B.yearly(d_ens, dy, (N,))[N], 4), "dd": round(B.max_dd(d_ens[dy == N]), 4),
                                 "members": [list(keys[i]) for i in top]},
                    "median_all": round(float(np.median([yrs[i][N] for i in range(len(keys))])), 4)}
        if N == FOLDS[-1]:
            final_W, final_d = Wens, d_ens
    ref = {"BTC buy & hold": eng.daily(eng.weights(np.ones(ctx.nD), "BTC", 0)),
           "equal-weight basket, always": eng.daily(eng.weights(np.ones(ctx.nD), "equal weight", 0)),
           "equal weight while BTC > MA100": eng.daily(eng.weights(regs["BTC>MA100"], "equal weight", 0))}
    doc = {"at": now(), "configs": len(keys), "regimes": len(regs), "baskets": list(eng.b4), "vol_targets": list(VOLT), "folds": folds,
           "final": {"chosen_on": f"{FIRST}-2025", "members": folds[2026]["ensemble"]["members"],
                     "years": {y: round(v, 4) for y, v in B.yearly(final_d, dy, YEARS).items()},
                     "dd_2020_25": round(B.max_dd(final_d[np.isin(dy, range(2020, 2026))]), 4)},
           "reference": {k: {y: round(v, 4) for y, v in B.yearly(d, dy, YEARS).items()} for k, d in ref.items()},
           "minutes": round((time.time() - t0) / 60, 1)}
    (OUT / "results.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    np.save(OUT / "final_W.npy", final_W.astype(np.float32))
    report(doc)
    progress(stage="done", done=len(keys), total=len(keys), minutes=doc["minutes"])
    return 0


def report(doc: dict) -> None:
    f = doc["folds"]
    L = ["# System 12 - BTC regime core, walk-forward", "",
         f"{doc['configs']:,} configurations ({doc['regimes']} regimes x {len(doc['baskets'])} baskets x {len(doc['vol_targets'])} sizings). "
         "Each year is read with what was chosen on the years before it. Costs charged. Each year from the same capital.", "",
         "| year | chosen on | single best (its rule) | average of the 20 best | median of all configs |", "|---|---|---|---|---|"]
    for N, x in f.items():
        L.append(f"| {N}{' (forward)' if int(N) == 2026 else ''} | {x['train']} | {x['best']['ret']:+.1%} <small>{' / '.join(map(str, x['best']['cfg']))}</small> | "
                 f"{x['ensemble']['ret']:+.1%} (DD {x['ensemble']['dd']:.0%}) | {x['median_all']:+.1%} |")
    L += ["", "Reference (no selection):", "", "| | " + " | ".join(str(y) for y in YEARS) + " |", "|---|" + "---|" * len(YEARS)]
    L.append("| System 11 (paper scale) | - | +59% | +96% | -12% | +38% | +19% | +8% | +1.5% |")
    for k, v in doc["reference"].items():
        L.append(f"| {k} | " + " | ".join(f"{v[y]:+.0%}" for y in YEARS) + " |")
    L += ["", "The 20 configurations chosen on 2019-2025 (System 12 for 2026):", ""] + [f"- {' / '.join(map(str, m))}" for m in doc["final"]["members"]]
    (OUT / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
