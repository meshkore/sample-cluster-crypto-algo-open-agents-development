"""System 12's 2026 trades for the Live view's Trades tab, in the same shape the tab already reads
(summary: lab/trades.json; heavy series: lab/trades_detail.json, served as /api/detail?id=__fwd100__).

The book is the walk-forward choice for 2026: the average of the 20 configurations chosen on 2019-2025.
A trade is a run of 4h bars where a coin is held on the same side (long or short). Out of sample.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import history_v2 as H

FROM = np.datetime64("2026-01-01", "ns").astype(np.int64)


def write(eng, sig: dict, W: np.ndarray, members: list[np.ndarray], names: list[str], lab, half: float) -> None:
    w = eng.w
    P4, P1 = w.P4, w.P["1d"]
    g4, c = P4["grid"], P4["close"]
    T, S = c.shape
    rows = np.flatnonzero(g4 >= FROM)
    a = rows[0]
    R = np.zeros_like(c)
    R[:-1] = np.nan_to_num(c[1:] / c[:-1] - 1)
    dW = np.abs(np.diff(np.r_[np.zeros((1, S)), W], axis=0))
    yi = np.clip(P4["year"] - H.Y0, 0, 2026 - H.Y0)
    pnl = W * R - dW * (half + w.imp["4h"][yi]) - W * w.fund4
    pnl[-1] = 0.0
    ts = lambda i: str(g4[i].astype("datetime64[ns]"))[:16]  # noqa: E731
    day_of = np.searchsorted(P1["grid"], g4, side="left") - 1
    btc = pd.Series(P1["close"][:, P1["coins"].index("BTCUSDT")])
    gate = (btc > btc.rolling(100, min_periods=100).mean()).values
    share = {}                                                   # share of the 20 configurations on each side
    for sgn in (1, -1):
        share[sgn] = np.mean([(np.sign(m) == sgn) & (np.abs(m) > 1e-9) for m in members], axis=0)
    trades = []
    for j in range(S):
        sg = np.sign(np.where(np.abs(W[:, j]) > 1e-6, W[:, j], 0))
        i = a
        while i < T:
            if sg[i] == 0:
                i += 1
                continue
            s0, side = i, sg[i]
            while s0 > 0 and sg[s0 - 1] == side:
                s0 -= 1
            e = i
            while e + 1 < T and sg[e + 1] == side:
                e += 1
            open_ = e + 1 >= T
            xi = min(e + 1, T - 1)
            px0, px1 = c[s0, j], c[xi, j]
            view = lambda k: {"t": ts(max(k - 1, 0)), "rank": round(float(share[side][k, j]), 3), "of": len(members),  # noqa: E731
                              "gate": bool(gate[max(day_of[k], 0)]), "member": True, "votes": int(round(share[side][k, j] * len(members)))}
            trades.append({"coin": P4["coins"][j].replace("USDT", ""), "side": "long" if side > 0 else "short",
                           "entry": ts(s0), "exit": None if open_ else ts(xi), "entry_px": H.sig(px0),
                           "exit_px": None if open_ else H.sig(px1), "last_px": H.sig(c[T - 1, j]),
                           "ret": round(float(side * (px1 / px0 - 1)), 4), "book_pnl": round(float(pnl[max(s0, a): e + 1, j].sum()), 5),
                           "w_max": round(float(np.abs(W[s0:e + 1, j]).max()), 4), "w_avg": round(float(np.abs(W[s0:e + 1, j]).mean()), 4),
                           "bars": int(e + 1 - s0), "before_window": bool(s0 < a), "open": bool(open_),
                           "exit_reason": None if open_ else "regime changed", "at_entry": view(s0), "at_exit": None if open_ else view(xi)})
            i = e + 1
    trades.sort(key=lambda t: t["entry"])
    # heavy series
    coins = sorted({t["coin"] for t in trades})
    rr = rows[::2]
    det = {"id": "system12", "kind": "s12", "built": H.now(), "t": [ts(i) for i in rr], "coins": {}, "trades": []}
    inds = {}
    for cn in coins:
        j = P4["coins"].index(cn + "USDT")
        ind = H.daily_indicators(P1["close"][:, j], P1["high"][:, j], P1["low"][:, j], P1["usd"][:, j])
        inds[cn] = ind
        dd = np.clip(day_of[rr], 0, None)
        r4 = lambda arr: [None if not np.isfinite(x) else H.sig(x) for x in arr]  # noqa: E731
        det["coins"][cn] = {"close": r4(c[rr, j]), "ema20": r4(ind["_ema20"].values[dd]), "ema50": r4(ind["_ema50"].values[dd]),
                            "ema200": r4(ind["_ema200"].values[dd]),
                            "rank": [round(float(max(share[1][i, j], share[-1][i, j])), 3) for i in rr],
                            "weight": [round(float(W[i, j]), 4) for i in rr]}
    for t in trades:
        j = P4["coins"].index(t["coin"] + "USDT")
        side = {}
        for nm, when in (("entry", t["entry"]), ("exit", t["exit"])):
            if when is None:
                side[nm] = None
                continue
            i = int(np.searchsorted(g4, np.datetime64(when, "ns").astype("int64")))
            dk = int(day_of[min(i, T - 1)])
            sgn = 1 if t["side"] == "long" else -1
            side[nm] = {"daily_close_at": str((P1["grid"][dk] - 1).astype("datetime64[ns]"))[:10],
                        "ind": {k: (None if not np.isfinite(v.values[dk]) else round(float(v.values[dk]), 5))
                                for k, v in inds[t["coin"]].items() if not k.startswith("_")},
                        "configs_holding": [names[q] for q, m in enumerate(members) if np.sign(m[min(i, T - 1), j]) == sgn and abs(m[min(i, T - 1), j]) > 1e-9],
                        "configs_before": []}
        det["trades"].append(side)
    # market context (daily)
    d1 = np.flatnonzero(P1["grid"] >= FROM)
    c1 = P1["close"]
    jb, je = P1["coins"].index("BTCUSDT"), P1["coins"].index("ETHUSDT")
    r1 = np.zeros_like(c1)
    r1[1:] = c1[1:] / c1[:-1] - 1
    ew = np.nanmean(np.where(P1["member"] & np.isfinite(r1), r1, np.nan), axis=1)
    day = [str((P1["grid"][k] - 1).astype("datetime64[ns]"))[:10] for k in d1]
    ma50 = pd.DataFrame(c1).rolling(50, min_periods=25).mean().values
    ctx = {"days": day, "btc": [round(float(c1[k, jb]), 2) for k in d1], "eth": [round(float(c1[k, je]), 2) for k in d1],
           "ew_index": [round(float(x), 4) for x in np.cumprod(1 + np.nan_to_num(ew[d1]))],
           "breadth": [round(float(np.nansum((c1[k] > ma50[k]) & P1["member"][k]) / max(P1["member"][k].sum(), 1)), 3) for k in d1],
           "gate": [bool(gate[k]) for k in d1]}
    try:
        for k, ser in H.external(len(d1) + 40).items():
            mp, last, vals = dict(ser), None, []
            for d in day:
                last = mp.get(d, last)
                vals.append(last)
            ctx[k] = vals
    except Exception as exc:  # noqa: BLE001
        print(f"external: {exc}", flush=True)
    det["context"] = ctx
    summary = {"id": "system12", "built": det["built"], "from": ts(a), "to": ts(T - 1), "trades": trades, "context_days": len(day)}
    det["trades_summary"] = trades
    (lab / "trades_detail.json").write_text(json.dumps(det, default=str), encoding="utf-8")
    (lab / "trades.json").write_text(json.dumps(summary, default=str), encoding="utf-8")
