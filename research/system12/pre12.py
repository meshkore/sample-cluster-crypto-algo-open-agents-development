"""System 12 - the state BEFORE a signal (operator 2026-10-22: "the 4-20 candles before a buy or sell signal - their shape,
range, volume, speed - may tell whether the order is right; people trade candle figures, so they may carry information").

A study first, a filter only if the study finds something:
  1. Entries: every time one of the 20 configurations of a fold turns long or short (the 20 members make the sample ~20x
     larger than the book's own trades). Year N's entries come from fold N's members (chosen on years < N).
     Label: the entry's episode made money (that configuration, costs included).
  2. Features of the 4h candles before the entry (windows of 6, 18 and 42 bars = 1, 3, 7 days): speed and acceleration,
     range expansion, volume and taker-buy ratio, body and wick shares, up-candle share, distance to the 30-day high/low,
     and classic candle figures on the last bars (engulfing, hammer, inside bar, shooting star).
  3. Winners vs losers per feature (Mann-Whitney, Benjamini-Hochberg over all features), and an out-of-sample check:
     a regularised logistic model trained on years < N, AUC on year N (0.5 = no information).
  -> pre/PRE.md

    python research/system12/pre12.py
"""

from __future__ import annotations

import json

import numpy as np
from scipy.stats import mannwhitneyu
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import hyp12

OUT = hyp12.HERE / "pre"
YEARS = (2021, 2022, 2023, 2024, 2025)


def features(x):
    w, j = x.w, x.ib
    o, h, l, c = (w.P4[k][:, j].astype(float) for k in ("open", "high", "low", "close"))
    v = np.nan_to_num(w.P4["usd"][:, j].astype(float))
    tk = np.nan_to_num(w.P4["taker"][:, j].astype(float))
    T = len(c)
    lr = np.r_[0, np.diff(np.log(c))]
    rng = (h - l) / c
    body = np.abs(c - o) / np.maximum(h - l, 1e-12)
    upw = (h - np.maximum(o, c)) / np.maximum(h - l, 1e-12)
    low = (np.minimum(o, c) - l) / np.maximum(h - l, 1e-12)
    up = (c > o).astype(float)
    cs = lambda a: np.r_[0, np.cumsum(np.nan_to_num(a))]  # noqa: E731
    C = {k: cs(a) for k, a in dict(lr=lr, rng=rng, body=body, upw=upw, low=low, up=up, v=v, tk=tk, lr2=lr ** 2).items()}
    mean = lambda k, t, n: (C[k][t + 1] - C[k][max(0, t + 1 - n)]) / n  # noqa: E731
    F = {}

    def at(t):
        out = {}
        vol30 = np.sqrt(max(mean("lr2", t, 180), 1e-12))
        for n in (6, 18, 42):
            r = mean("lr", t, n) * n
            out[f"speed_{n}"] = r / (vol30 * np.sqrt(n))
            half = n // 2
            out[f"accel_{n}"] = (mean("lr", t, half) - mean("lr", max(t - half, 0), half)) / vol30
            out[f"range_x_{n}"] = mean("rng", t, n) / max(mean("rng", t, 180), 1e-12)
            out[f"volume_x_{n}"] = mean("v", t, n) / max(mean("v", t, 180), 1e-12)
            out[f"taker_{n}"] = mean("tk", t, n) / max(mean("v", t, n), 1e-12)
            out[f"body_{n}"] = mean("body", t, n)
            out[f"upper_wick_{n}"] = mean("upw", t, n)
            out[f"lower_wick_{n}"] = mean("low", t, n)
            out[f"up_share_{n}"] = mean("up", t, n)
        a = max(0, t - 180)
        out["dist_30d_high"] = c[t] / np.nanmax(h[a:t + 1]) - 1
        out["dist_30d_low"] = c[t] / np.nanmin(l[a:t + 1]) - 1
        if t >= 2:
            out["engulf_bull"] = float(c[t] > o[t] and c[t - 1] < o[t - 1] and c[t] >= o[t - 1] and o[t] <= c[t - 1])
            out["engulf_bear"] = float(c[t] < o[t] and c[t - 1] > o[t - 1] and o[t] >= c[t - 1] and c[t] <= o[t - 1])
            out["hammer"] = float(low[t] > 0.6 and body[t] < 0.3)
            out["shooting_star"] = float(upw[t] > 0.6 and body[t] < 0.3)
            out["inside_bar"] = float(h[t] < h[t - 1] and l[t] > l[t - 1])
        return out
    return at


def entries(lab, N):
    """Every entry of fold N's 20 members during year N (and during years < N for training, from the same members)."""
    import system12_ls as L
    res = json.loads((L.OUT / "results.json").read_text(encoding="utf-8"))
    out = []
    for r, b, v, s in res["folds"][str(N)]["ensemble"]["members"]:
        W = lab.eng.weights_ls(lab.regs[r], b, float(v), None if s == "None" else eval(s))  # noqa: S307
        side = np.sign(np.round(W.sum(axis=1), 6))
        ret = lab.x.ret4(W)
        t = 1
        while t < len(side):
            if side[t] != 0 and side[t] != side[t - 1]:
                a, sd = t, side[t]
                while t < len(side) and side[t] == sd:
                    t += 1
                out.append((a, int(sd), float(np.prod(1 + ret[a:t]) - 1), t - a))
            else:
                t += 1
    return out


def main() -> int:
    OUT.mkdir(exist_ok=True)
    lab = hyp12.Lab()
    x = lab.x
    at = features(x)
    rows = {}
    for N in YEARS:
        for a, sd, r, n in entries(lab, N):
            y = int(x.year[a])
            if y > N or y < 2019:
                continue
            key = (N, a, sd)
            if key not in rows:
                rows[key] = {"fold": N, "t": a, "year": y, "side": sd, "ret": r, "bars": n, **at(a - 1)}  # state up to the bar BEFORE
    data = list(rows.values())
    names = [k for k in data[0] if k not in ("fold", "t", "year", "side", "ret", "bars")]
    # descriptive: year-N entries of fold N only (each entry once), winners vs losers
    test = [d for d in data if d["year"] == d["fold"]]
    win = [d for d in test if d["ret"] > 0]
    los = [d for d in test if d["ret"] <= 0]
    stats = []
    for k in names:
        a = np.array([d[k] for d in win], dtype=float)
        b = np.array([d[k] for d in los], dtype=float)
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        p = mannwhitneyu(a, b).pvalue if len(a) > 5 and len(b) > 5 and (np.ptp(a) > 0 or np.ptp(b) > 0) else 1.0
        stats.append((k, float(np.median(a)), float(np.median(b)), float(p)))
    ps = np.array([s[3] for s in stats])
    order = np.argsort(ps)
    q = np.empty_like(ps)
    m = len(ps)
    q[order] = np.minimum.accumulate((ps[order] * m / np.arange(1, m + 1))[::-1])[::-1]
    # predictive, out of sample: train on entries in years < N (from fold N's members), test on year N
    auc = {}
    for N in YEARS:
        tr = [d for d in data if d["fold"] == N and d["year"] < N]
        te = [d for d in data if d["fold"] == N and d["year"] == N]
        if len(tr) < 50 or len(te) < 10:
            continue
        X = lambda S: np.nan_to_num(np.array([[d[k] for k in names] + [d["side"]] for d in S], dtype=float))  # noqa: E731
        y = lambda S: np.array([d["ret"] > 0 for d in S], dtype=int)  # noqa: E731
        mdl = make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=2000)).fit(X(tr), y(tr))
        p = mdl.predict_proba(X(te))[:, 1]
        yt = y(te)
        cut = p >= np.median(p)
        auc[N] = {"n": len(te), "auc": round(float(roc_auc_score(yt, p)), 3) if 0 < yt.mean() < 1 else None,
                  "win_rate": round(float(yt.mean()), 3), "win_rate_top_half": round(float(yt[cut].mean()), 3),
                  "win_rate_bottom_half": round(float(yt[~cut].mean()), 3),
                  "mean_ret_top": round(float(np.mean([d["ret"] for d, c in zip(te, cut) if c])), 4),
                  "mean_ret_bottom": round(float(np.mean([d["ret"] for d, c in zip(te, cut) if not c])), 4)}
    L = ["# System 12 - the state before a signal", "",
         f"{len(test)} entries in 2021-2025 (the 20 configurations of each year's book, each entry once), "
         f"{len(win)} winners, {len(los)} losers. Features read on the 4h candles BEFORE the entry bar.", "",
         "## Out of sample: a model trained on earlier years, read on year N", "",
         "| year | entries | AUC (0.5 = nothing) | win rate | win rate, model's top half | bottom half | mean return top | bottom |",
         "|---|---|---|---|---|---|---|---|"]
    for N, a in auc.items():
        L.append(f"| {N} | {a['n']} | {a['auc']} | {a['win_rate']:.0%} | {a['win_rate_top_half']:.0%} | {a['win_rate_bottom_half']:.0%} | "
                 f"{a['mean_ret_top']:+.2%} | {a['mean_ret_bottom']:+.2%} |")
    L += ["", "## Winners vs losers, feature by feature (q = p corrected for testing many features; < 0.05 = real difference)", "",
          "| feature | winners (median) | losers (median) | p | q |", "|---|---|---|---|---|"]
    for i in order:
        k, a, b, p = stats[i]
        L.append(f"| {k} | {a:+.3f} | {b:+.3f} | {p:.3f} | {q[i]:.3f} |")
    (OUT / "PRE.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    # For hypothesis H034: for every bar of year N, P(an entry here wins) for a long and for a short, from a model trained on
    # entries of years < N only (fold N's members; 2026 uses fold 2025's). H034 reads it at the start of each book trade.
    T = x.T
    pl, psh = np.full(T, np.nan), np.full(T, np.nan)
    for N in YEARS + (2026,):
        fold = min(N, 2025)
        tr = [d for d in data if d["fold"] == fold and d["year"] < N]
        if len(tr) < 50:
            continue
        X = lambda S: np.nan_to_num(np.array([[d[k] for k in names] + [d["side"]] for d in S], dtype=float))  # noqa: E731
        mdl = make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=2000)).fit(
            X(tr), np.array([d["ret"] > 0 for d in tr], dtype=int))
        idx = np.flatnonzero(x.year == N)
        feats = [at(t - 1) for t in idx]
        for sd, out in ((1, pl), (-1, psh)):
            M = np.nan_to_num(np.array([[f[k] for k in names] + [sd] for f in feats], dtype=float))
            out[idx] = mdl.predict_proba(M)[:, 1]
    np.save(OUT / "prob_long.npy", pl.astype(np.float32))
    np.save(OUT / "prob_short.npy", psh.astype(np.float32))
    (OUT / "auc.json").write_text(json.dumps(auc, indent=1), encoding="utf-8")
    print("\n".join(L[:14 + len(auc)]))
    print("\n".join(L[-len(stats):][:8]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
