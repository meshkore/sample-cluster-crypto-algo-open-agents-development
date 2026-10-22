"""System 12 - the second layer (operator 2026-10-22: "a decision tree that, when the system decides to buy or sell, uses RSI,
averages, crosses... to correct the decision; and study every losing trade to find what it had in common").

Two outputs, both strictly walk-forward:
  1. hyp/META.md - the autopsy: every trade (long or short episode) of the walk-forward chain, the market at its entry,
     losers vs winners feature by feature, and the rules of the tree trained on 2019-2025 (to READ, not to trade).
  2. hyp/meta_prob.npy - for every 4h bar in a position, the probability that the position's direction is right over the
     next 7 days, predicted by a depth-3 tree trained ONLY on years before that bar's year (purged 7 days before the
     year starts). Hypothesis H031 (hypotheses12.py) reads it and cuts exposure where the tree has no confidence.

Positions used for training rows of year j are the champion of fold j (chosen on years < j), so no future choice leaks in.

    python research/system12/meta12.py
"""

from __future__ import annotations

import json

import numpy as np
from sklearn.tree import DecisionTreeClassifier, export_text

import gen12
import hyp12
import hypotheses12 as HY
from hypotheses12 import D, roll

OUT = hyp12.OUT
FWD_BARS = 7 * D
YEARS = tuple(range(2019, 2027))


def features(x) -> tuple[np.ndarray, list[str]]:
    b, e = x.btc, x.eth
    back = lambda y, n: y / np.r_[np.full(n, y[0]), y[:-n]] - 1  # noqa: E731
    r = np.r_[0, np.diff(np.log(b))]
    ma = {n: roll(b, n * D, "mean") for n in (20, 50, 100, 200)}
    f = {
        "btc_ret_7d": back(b, 7 * D), "btc_ret_30d": back(b, 30 * D), "btc_ret_90d": back(b, 90 * D),
        **{f"btc_vs_ma{n}": b / ma[n] - 1 for n in ma},
        "ma50_slope_10d": back(ma[50], 10 * D),
        "ma20_vs_ma50": ma[20] / ma[50] - 1,
        "rsi_14d": gen12._rsi(b, 14 * D),
        "vol_30d": roll(r, 30 * D, "std") * np.sqrt(365 * D),
        "vol_7d_vs_90d": roll(r, 7 * D, "std") / roll(r, 90 * D, "std"),
        "dd_from_90d_high": 1 - b / roll(b, 90 * D, "max"),
        "funding_7d": roll(np.nan_to_num(x.fund[:, x.ib]), 7 * D, "mean"),
        "ethbtc_30d": back(e / b, 30 * D),
        "breadth_50d": gen12.HY._breadth(x),
        "alt_lead_30d": HY._alt_lead(x, 30),
    }
    names = list(f)
    return np.column_stack([np.nan_to_num(f[k], nan=0.0, posinf=0.0, neginf=0.0) for k in names]), names


def chain_W(lab, champ, reg) -> np.ndarray:
    """Year j traded by the champion of fold j (2019-2020 use fold 2021, chosen on 2019-2020)."""
    W = np.zeros_like(lab.base[2021])
    for j in YEARS:
        N = max(j, 2021)
        m = lab.x.year == j
        W[m] = lab.champion_W(champ, N, reg)[m]
    return W


def episodes(x, W):
    side = np.sign(np.round(W.sum(axis=1), 6))
    r = x.ret4(W)
    out, t = [], 0
    while t < x.T:
        if side[t] == 0:
            t += 1
            continue
        s, a = side[t], t
        while t < x.T and side[t] == s:
            t += 1
        out.append({"start": a, "end": t, "side": int(s), "ret": float(np.prod(1 + r[a:t]) - 1)})
    return out


def main() -> int:
    import hypotheses12
    reg = {h.id: h for h in hypotheses12.ALL + gen12.load()}
    lab = hyp12.Lab()
    x = lab.x
    champ = hyp12.load_champ()
    W = chain_W(lab, champ, reg)
    F, names = features(x)
    side = np.sign(np.round(W.sum(axis=1), 6))
    basket = 0.5 * (x.btc + x.eth)
    fwd = np.r_[basket[FWD_BARS:] / basket[:-FWD_BARS] - 1, np.full(FWD_BARS, np.nan)]
    y = (side * fwd > 0).astype(int)
    X = np.column_stack([F, side])
    cols = names + ["side"]
    year = x.year
    rows = (side != 0) & np.isfinite(fwd) & (np.arange(x.T) % D == 0)      # one sample a day: less autocorrelation

    prob = np.full(x.T, np.nan)
    acc = {}
    tree_kw = dict(max_depth=3, min_samples_leaf=40, class_weight="balanced", random_state=0)
    for k in range(2021, 2027):
        k0 = np.flatnonzero(year == k)[0]
        tr = rows & (np.arange(x.T) + FWD_BARS < k0) & (year >= 2019)        # purge: labels must end before year k
        if tr.sum() < 100:
            continue
        m = DecisionTreeClassifier(**tree_kw).fit(X[tr], y[tr])
        te = (year == k) & (side != 0)
        prob[te] = m.predict_proba(X[te])[:, 1]
        ev = te & rows & np.isfinite(fwd)
        if ev.sum():
            pr = prob[ev] >= 0.5
            acc[k] = {"n": int(ev.sum()), "base_rate": round(float(y[ev].mean()), 3),
                      "hit_when_trusted": round(float(y[ev][pr].mean()) if pr.any() else float("nan"), 3),
                      "hit_when_doubted": round(float(y[ev][~pr].mean()) if (~pr).any() else float("nan"), 3),
                      "share_doubted": round(float((~pr).mean()), 3)}
    np.save(OUT / "meta_prob.npy", prob.astype(np.float32))

    # the autopsy (read-only): episodes of the chain, losers vs winners at entry
    eps = [e for e in episodes(x, W) if 2021 <= year[e["start"]] <= 2025]          # 2026 is never used to choose
    L = ["# System 12 - second layer: trade autopsy and decision tree", "",
         f"Walk-forward chain 2021-2025 (each year the champion chosen on earlier years): {len(eps)} trades, "
         f"{sum(e['ret'] < 0 for e in eps)} losers.", "",
         "## Out-of-sample check of the tree (each year predicted by a tree trained on earlier years only)", "",
         "| year | days in position | right direction (base) | when the tree trusts | when it doubts | share doubted |", "|---|---|---|---|---|---|"]
    for k, a in acc.items():
        L.append(f"| {k} | {a['n']} | {a['base_rate']:.0%} | {a['hit_when_trusted']:.0%} | {a['hit_when_doubted']:.0%} | {a['share_doubted']:.0%} |")
    L += ["", "A useful layer shows 'when it doubts' clearly BELOW 'when it trusts' in most years.", "",
          "## Losers vs winners at entry (median)", "", "| feature | losers | winners |", "|---|---|---|"]
    los = [e for e in eps if e["ret"] < 0]
    win = [e for e in eps if e["ret"] >= 0]
    for i, n in enumerate(names):
        lv = np.median([F[e["start"], i] for e in los]) if los else np.nan
        wv = np.median([F[e["start"], i] for e in win]) if win else np.nan
        L.append(f"| {n} | {lv:+.3f} | {wv:+.3f} |")
    L += ["", "## The 15 worst trades", "", "| entry | side | days | return | RSI | BTC vs MA50 | 30d return |", "|---|---|---|---|---|---|---|"]
    gi = {n: i for i, n in enumerate(names)}
    for e in sorted(eps, key=lambda e: e["ret"])[:15]:
        t = e["start"]
        L.append(f"| {str(x.w.P4['grid'][t].astype('datetime64[ns]'))[:10]} | {'long' if e['side'] > 0 else 'short'} | "
                 f"{(e['end'] - t) / D:.0f} | {e['ret']:+.1%} | {F[t, gi['rsi_14d']]:.0f} | {F[t, gi['btc_vs_ma50']]:+.1%} | {F[t, gi['btc_ret_30d']]:+.1%} |")
    tr = rows & (year <= 2025)
    m = DecisionTreeClassifier(**tree_kw).fit(X[tr], y[tr])
    L += ["", "## The tree trained on 2019-2025 (to read; trading uses the per-year trees above)", "", "```",
          export_text(m, feature_names=cols, decimals=3), "```"]
    (OUT / "META.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (OUT / "meta_acc.json").write_text(json.dumps(acc, indent=1), encoding="utf-8")
    print("\n".join(L[:20]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
