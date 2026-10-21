"""System 12, step 2 - long AND short on perpetuals (operator go 2026-10-21: "go as far as you can").

Same regime x basket x sizing search as system12.py, plus a SHORT side: when the regime is bearish (score below
a threshold), short BTC, BTC+ETH or the equal-weight basket on USD-M perpetuals instead of sitting in cash.
The whole book is on perpetuals: 0.10%/side + impact, funding charged (a short receives positive funding),
only coins whose perpetual existed at the time.

    short basket   none | BTC | BTC+ETH | equal weight
    threshold      short only when the regime score is 0 (fully bearish) or below 0.5
    short size     50% or 100% of the bearish score, under the same volatility target

Honesty as in system12.py: year N chosen on 2019..N-1 (single best and average of the 20 best), 2026 forward only.
Runs in chunks so several processes share the work:

    python research/system12/system12_ls.py --chunk 0 --of 3      (x3, in parallel)
    python research/system12/system12_ls.py --merge --of 3          -> out_ls/{results.json, REPORT.md}
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import system12 as S
from system12 import B, H, K, R  # noqa: E402
import lab_v2 as LV  # noqa: E402

OUT = S.HERE / "out_ls"
LONG_BASKETS = ("BTC", "BTC+ETH", "equal weight", "System 11 model picks")
VOLT = (0.0, 0.4, 0.6)
SHORTS = [None] + [(b, th, sz) for b in ("BTC", "BTC+ETH", "equal weight") for th in (0.0, 0.5) for sz in (0.5, 1.0)]


def keys(regs) -> list:
    return [(r, b, v, s) for r in regs for b in LONG_BASKETS for v in VOLT for s in SHORTS]


class LS(S.Engine):
    def __init__(self, *a):
        super().__init__(*a)
        self.can = self.w.perp["4h"] & np.isfinite(self.w.P4["close"])

    def vt_factor(self, basket: str, vt: float) -> np.ndarray:
        if not vt:
            return np.ones(self.ctx.nD)
        vol = pd.Series(self.bret[basket]).rolling(30, min_periods=20).std().values * np.sqrt(365)
        return np.where(np.isfinite(vol) & (vol > 0), np.clip(vt / np.where(vol > 0, vol, 1), 0, 1), 0.0)

    def to4(self, e: np.ndarray) -> np.ndarray:
        e4 = e[np.clip(self.ctx.dk, 0, None)]
        e4[self.ctx.dk < 0] = 0.0
        return e4

    def weights_ls(self, reg, basket, vt, short) -> np.ndarray:
        W = self.weights(reg, basket, vt)
        if short:
            sb, th, sz = short
            bear = np.where(reg <= th + 1e-9, 1.0 - reg, 0.0) * sz * self.vt_factor(sb, vt)
            bear = np.floor(bear * 4 + 1e-9) / 4
            W = W - self.b4[sb] * self.to4(bear)[:, None]
        return np.where(self.can, W, 0.0)

    def daily_ls(self, W) -> np.ndarray:
        r, _ = H.bar_returns(self.w, W, LV.PERP_HALF, self.w.fund4)
        return H.to_daily(self.w, r)[0]


def setup():
    cut = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "ns").astype("int64")
    w = H.world(S.CAP, int(cut))
    ctx = K.Ctx(w)
    T, Sx = w.P4["close"].shape
    z = np.load(R.CACHE / "base.npz")
    Wm = z["s2_W"].astype(float)
    Wm = np.r_[Wm, np.zeros((T - Wm.shape[0], Sx))]
    tot = Wm.sum(axis=1, keepdims=True)
    mlp4 = np.where(tot > 1e-9, Wm / np.maximum(tot, 1e-12), 0.0)
    early = w.P4["year"] < 2020
    mlp4[early] = ctx.to4h(ctx.ew())[early]
    eng = LS(w, ctx, S.baskets(ctx, mlp4), mlp4)
    return eng, S.regimes(S.signals(ctx))


def chunk(i: int, of: int) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    eng, regs = setup()
    K_ = keys(regs)
    mine = list(range(i, len(K_), of))
    dy = eng.dy
    obj = np.zeros((len(mine), len(S.FOLDS)), dtype=np.float32)
    yrs = np.zeros((len(mine), len(S.YEARS)), dtype=np.float32)
    t0 = time.time()
    for n, k in enumerate(mine):
        r, b, v, s = K_[k]
        d = eng.daily_ls(eng.weights_ls(regs[r], b, v, s))
        for f, N in enumerate(S.FOLDS):
            obj[n, f] = B.objective_value(d, dy, tuple(range(S.FIRST, N)))[0]
        yy = B.yearly(d, dy, S.YEARS)
        yrs[n] = [yy[y] for y in S.YEARS]
        if n % 250 == 0:
            (OUT / f"progress_{i}.json").write_text(json.dumps({"done": n, "of": len(mine), "minutes": round((time.time() - t0) / 60, 1)}))
    np.savez(OUT / f"chunk_{i}.npz", idx=np.array(mine), obj=obj, yrs=yrs)
    (OUT / f"progress_{i}.json").write_text(json.dumps({"done": len(mine), "of": len(mine), "minutes": round((time.time() - t0) / 60, 1)}))
    return 0


def merge(of: int) -> int:
    eng, regs = setup()
    K_ = keys(regs)
    obj = np.zeros((len(K_), len(S.FOLDS)), dtype=np.float32)
    yrs = np.zeros((len(K_), len(S.YEARS)), dtype=np.float32)
    for i in range(of):
        z = np.load(OUT / f"chunk_{i}.npz")
        obj[z["idx"]], yrs[z["idx"]] = z["obj"], z["yrs"]
    dy = eng.dy
    folds = {}
    longonly = np.array([k[3] is None for k in K_])
    for f, N in enumerate(S.FOLDS):
        yi = S.YEARS.index(N)
        order = np.argsort(-obj[:, f])
        top = order[:S.TOPK]
        W = sum(eng.weights_ls(regs[K_[i][0]], *K_[i][1:]) for i in top) / len(top)
        d = eng.daily_ls(W)
        folds[N] = {"train": f"{S.FIRST}-{N - 1}",
                    "best": {"cfg": [str(x) for x in K_[order[0]]], "ret": round(float(yrs[order[0], yi]), 4)},
                    "ensemble": {"ret": round(B.yearly(d, dy, (N,))[N], 4), "dd": round(B.max_dd(d[dy == N]), 4),
                                 "members": [[str(x) for x in K_[i]] for i in top],
                                 "short_share": round(float(np.mean([K_[i][3] is not None for i in top])), 2)},
                    "median_all": round(float(np.median(yrs[:, yi])), 4),
                    "median_longonly": round(float(np.median(yrs[longonly, yi])), 4)}
        if N == S.FOLDS[-1]:
            final_W, final_d = W, d
    doc = {"at": S.now(), "configs": len(K_), "folds": folds,
           "final": {"chosen_on": f"{S.FIRST}-2025", "members": folds[S.FOLDS[-1]]["ensemble"]["members"],
                     "years": {y: round(v, 4) for y, v in B.yearly(final_d, dy, S.YEARS).items()},
                     "dd_2020_25": round(B.max_dd(final_d[np.isin(dy, range(2020, 2026))]), 4)}}
    (OUT / "results.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    np.save(OUT / "final_W.npy", final_W.astype(np.float32))
    L = ["# System 12 step 2 - long and short on perpetuals, walk-forward", "",
         f"{len(K_):,} configurations. Year N uses what was chosen on 2019..N-1. Perp costs + funding. Each year from the same capital.", "",
         "| year | single best | average of the 20 best | share of the 20 that short | median all | median long-only |", "|---|---|---|---|---|---|"]
    for N, x in folds.items():
        L.append(f"| {N}{' (forward)' if N == 2026 else ''} | {x['best']['ret']:+.1%} <small>{' / '.join(x['best']['cfg'])}</small> | "
                 f"{x['ensemble']['ret']:+.1%} (DD {x['ensemble']['dd']:.0%}) | {x['ensemble']['short_share']:.0%} | {x['median_all']:+.1%} | {x['median_longonly']:+.1%} |")
    L += ["", f"Chosen on 2019-2025 (System 12 for 2026), its years in-sample: "
          + ", ".join(f"{y} {v:+.0%}" for y, v in doc["final"]["years"].items()) + f"; DD 2020-25 {doc['final']['dd_2020_25']:.0%}", ""]
    L += [f"- {' / '.join(m)}" for m in doc["final"]["members"]]
    (OUT / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:14]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=0)
    ap.add_argument("--of", type=int, default=3)
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    return merge(a.of) if a.merge else chunk(a.chunk, a.of)


if __name__ == "__main__":
    raise SystemExit(main())
