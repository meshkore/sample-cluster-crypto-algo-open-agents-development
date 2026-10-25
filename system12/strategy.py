"""System 12 - the strategy: BTC trend regime, long BTC+ETH in bull phases, half short in bear phases, on USD-M perps.

The book is the average of 20 frozen configurations (chosen walk-forward on 2019-2025 from 75,504; see
docs/ARCHITECTURE.md), plus two overlays the hypothesis loop adopted out of sample (champion v6, G00233):
    trail_short   cover the short leg once BTC rises 10% above its low since the short began
    trend_convex  long leg x clip(1 + BTC 30-day return / 0.4, 0.5, 2), gross capped at 100%
A decision is taken at a 4h close and trades from the next bar. Daily signals are read at the last daily close
before the 4h decision. Everything here is deterministic and causal: no seeds, no fitted parameters.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from . import data

HERE = Path(__file__).resolve().parent
SELECTION = json.loads((HERE / "selection.json").read_text(encoding="utf-8"))
Y0 = 2018  # first year on the grids (signals warm up from here)
D = 6  # 4h bars per day
HALF_COST = 0.0010  # per side, USD-M perps
BOOK_FOR_IMPACT = 100_000.0  # square-root impact is priced for a book of this size


def year_of(ns: np.ndarray) -> np.ndarray:
    """A bar stamped at its close belongs to the year its open is in."""
    return (np.asarray(ns, dtype=np.int64) - 1).astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970


# ------------------------------------------------------------------ the world: aligned BTC/ETH panels


def world(cut_ns: int | None = None) -> SimpleNamespace:
    k4 = {c: data.klines(c, "4h") for c in data.COINS}
    k1 = {c: data.klines(c, "1d") for c in data.COINS}
    fr = {c: data.funding(c) for c in data.COINS}
    w = SimpleNamespace(coins=list(data.COINS))
    for tf, k in (("4h", k4), ("1d", k1)):
        grid = np.unique(np.concatenate([np.asarray(v.index, dtype=np.int64) for v in k.values()]))
        if cut_ns is not None:
            grid = grid[grid < cut_ns]
        grid = grid[year_of(grid) >= Y0]
        p = {"grid": grid, "year": year_of(grid)}
        for col in ("close", "usd"):
            p[col] = np.column_stack([k[c][col].reindex(grid).values for c in data.COINS]).astype(float)
        setattr(w, "p4" if tf == "4h" else "p1", p)
    g4 = w.p4["grid"]
    opens = g4 - data.STEP["4h"]
    w.fund4 = np.zeros((len(g4), len(data.COINS)))
    w.perp4 = np.zeros((len(g4), len(data.COINS)), dtype=bool)
    for j, c in enumerate(data.COINS):
        t = np.asarray(fr[c].index, dtype=np.int64)
        i = np.searchsorted(t, opens, side="right") - 1
        ok = i >= 0
        w.fund4[ok, j] = fr[c].values[i[ok]] / 2  # 8h settlement spread over two 4h bars
        w.perp4[:, j] = g4 >= t[0]
    prev = np.r_[g4[0], g4[:-1]]
    w.dk = np.searchsorted(w.p1["grid"], prev, side="right") - 1  # last daily close known at the 4h decision
    w.imp = impact(w.p4)
    return w


def impact(p4: dict) -> np.ndarray:
    """Square-root impact per (year - Y0, coin): daily vol x sqrt(book / 3 / median daily dollar volume of the year before)."""
    c, usd, yr = p4["close"], p4["usd"], p4["year"]
    out = np.zeros((2100 - Y0, c.shape[1]))
    for i, y in enumerate(range(Y0, 2100)):
        for j in range(c.shape[1]):
            sel = (yr == y - 1) & np.isfinite(c[:, j])
            if sel.sum() < 30 * D:
                sel = (yr == y) & np.isfinite(c[:, j])
            if sel.sum() < 10 * D:
                out[i, j] = 0.003
                continue
            cd = c[sel, j][D - 1 :: D]
            ud = usd[sel, j][: (sel.sum() // D) * D].reshape(-1, D).sum(axis=1)
            sig = np.std(np.diff(np.log(cd))) if len(cd) > 2 else 0.05
            out[i, j] = float(sig * np.sqrt(BOOK_FOR_IMPACT / 3 / max(np.median(ud), 1.0)))
    return out


# ------------------------------------------------------------------ regime signals (daily, 0..1)


def signals(w) -> dict[str, np.ndarray]:
    btc = pd.Series(w.p1["close"][:, 0])
    sm = lambda n: btc.rolling(n, min_periods=n).mean()  # noqa: E731
    out = {f"BTC>MA{n}": (btc > sm(n)).values.astype(float) for n in (20, 50, 100, 150, 200)}
    out["BTC MA ensemble 20/50/100/200"] = np.mean([out[f"BTC>MA{n}"] for n in (20, 50, 100, 200)], axis=0)
    out["BTC MA-ratio rules (Detzel)"] = np.mean(
        [(sm(fast) > sm(slow)).values for fast in (5, 10, 20) for slow in (50, 100, 200)], axis=0
    ).astype(float)
    for n in (14, 30, 60):
        out[f"BTC {n}d momentum"] = (btc / btc.shift(n) > 1).values.astype(float)
    return {k: np.nan_to_num(v) for k, v in out.items()}


def regime(sig: dict, name: str) -> np.ndarray:
    if name.startswith("mean("):
        a, b = name[5:-1].split(" | ")
        return (sig[a] + sig[b]) / 2
    if " AND " in name:
        a, b = name.split(" AND ")
        return np.minimum(sig[a], sig[b])
    return sig[name]


# ------------------------------------------------------------------ the 20 members


class Engine:
    def __init__(self, w):
        self.w = w
        C = pd.DataFrame(w.p1["close"])
        R1 = np.nan_to_num((C / C.shift(1) - 1).values)
        self.bret = {"BTC": R1[:, 0], "BTC+ETH": 0.5 * R1[:, 0] + 0.5 * R1[:, 1]}
        nD = len(w.p1["grid"])
        daily = {"BTC": np.tile([1.0, 0.0], (nD, 1)), "BTC+ETH": np.tile([0.5, 0.5], (nD, 1))}
        self.live = np.isfinite(w.p4["close"])
        self.b4 = {k: self._basket4(v) for k, v in daily.items()}
        self.can = w.perp4 & self.live

    def _to4(self, e: np.ndarray) -> np.ndarray:
        e4 = e[np.clip(self.w.dk, 0, None)].copy()
        e4[self.w.dk < 0] = 0.0
        return e4

    def _basket4(self, Dw: np.ndarray) -> np.ndarray:
        W = self._to4(Dw)
        W = np.where(self.live, W, 0.0)
        s = W.sum(axis=1, keepdims=True)
        return np.where(s > 1.0, W / np.maximum(s, 1e-12), np.clip(W, 0, None))

    def _vol(self, basket: str) -> np.ndarray:
        return pd.Series(self.bret[basket]).rolling(30, min_periods=20).std().values * np.sqrt(365)

    def exposure(self, reg, basket, vt) -> np.ndarray:
        e = reg.copy()
        if vt:
            vol = self._vol(basket)
            e = e * np.clip(vt / np.where(np.isfinite(vol) & (vol > 0), vol, np.inf), 0, 1)
            e = np.where(np.isfinite(vol), e, 0.0)
        return np.floor(e * 4 + 1e-9) / 4  # steps of 25%

    def vt_factor(self, basket, vt) -> np.ndarray:
        if not vt:
            return np.ones(len(self.w.p1["grid"]))
        vol = self._vol(basket)
        return np.where(np.isfinite(vol) & (vol > 0), np.clip(vt / np.where(vol > 0, vol, 1), 0, 1), 0.0)

    def member(self, reg, basket, vt, short) -> np.ndarray:
        W = self.b4[basket] * self._to4(self.exposure(reg, basket, vt))[:, None]
        W = np.where(self.live, W, 0.0)
        if short:
            sb, th, sz = short
            bear = np.where(reg <= th + 1e-9, 1.0 - reg, 0.0) * sz * self.vt_factor(sb, vt)
            bear = np.floor(bear * 4 + 1e-9) / 4
            W = W - self.b4[sb] * self._to4(bear)[:, None]
        return np.where(self.can, W, 0.0)


def base_weights(w, eng: Engine | None = None) -> np.ndarray:
    eng = eng or Engine(w)
    sig = signals(w)
    ms = SELECTION["members"]
    return sum(eng.member(regime(sig, r), b, float(v), None if s is None else tuple(s)) for r, b, v, s in ms) / len(ms)


# ------------------------------------------------------------------ overlays (champion v6, G00233)


def _ffill(x: np.ndarray) -> np.ndarray:
    x = x.astype(float).copy()
    idx = np.where(np.isfinite(x), np.arange(len(x)), 0)
    np.maximum.accumulate(idx, out=idx)
    x = x[idx]
    x[~np.isfinite(x)] = np.nan
    return x


def _lag(m: np.ndarray) -> np.ndarray:
    out = np.empty_like(m, dtype=float)
    out[:1], out[1:] = m[0], m[:-1]
    return out


def _cap(W: np.ndarray, g: float = 1.0) -> np.ndarray:
    gross = np.abs(W).sum(axis=1)
    return W * np.minimum(1.0, g / np.maximum(gross, 1e-9))[:, None]


def trail_short(btc: np.ndarray, W: np.ndarray, p: float) -> np.ndarray:
    """Inside each short episode, cover (multiplier 0) once BTC closes more than p above its low since the episode began."""
    on = np.maximum(-W, 0).sum(axis=1) > 1e-9
    m, start, k, lo = np.ones(len(W)), -1, 1.0, np.nan
    for t in range(len(W)):
        if not on[t]:
            start = -1
            continue
        if start < 0:
            start, k, lo = t, 1.0, btc[t]
        lo = min(lo, btc[t])
        k = 0.0 if k == 0 or btc[t] > lo * (1 + p) else 1.0
        m[t] = k
    m = _lag(m)
    return np.where(W < 0, W * m[:, None], W)


def trend_convex(btc: np.ndarray, W: np.ndarray, p: float) -> np.ndarray:
    m30 = btc / np.r_[np.full(30 * D, btc[0]), btc[: -30 * D]] - 1
    m = _lag(np.clip(1 + np.nan_to_num(m30) / p, 0.5, 2.0))
    return _cap(np.where(W > 0, W * m[:, None], W))


OVERLAYS = {"trail_short": trail_short, "trend_convex": trend_convex}


def weights(w) -> np.ndarray:
    """The executed target weights (T4 x [BTC, ETH]); row t is decided at the close of bar t and held to t+1."""
    W = base_weights(w)
    btc = _ffill(w.p4["close"][:, 0])
    for name, p in SELECTION["overlays"]:
        W = OVERLAYS[name](btc, W, float(p))
    return W


# ------------------------------------------------------------------ accounting


def bar_returns(w, W: np.ndarray) -> np.ndarray:
    """Net 4h returns: price move + funding (a long pays positive funding) - (0.10% + impact) per unit traded."""
    c = w.p4["close"]
    R = np.zeros_like(c)
    R[:-1] = np.nan_to_num(c[1:] / c[:-1] - 1)
    W = np.where(np.isfinite(c), W, 0.0)
    dW = np.abs(np.diff(np.r_[np.zeros((1, W.shape[1])), W], axis=0))
    yi = np.clip(w.p4["year"] - Y0, 0, w.imp.shape[0] - 1)
    cost = (dW * (HALF_COST + w.imp[yi])).sum(axis=1)
    r = (W * R).sum(axis=1) - cost - (W * w.fund4).sum(axis=1)
    r[-1] = 0.0  # the last bar's outcome is not known yet
    return r


def to_daily(w, r: np.ndarray):
    day = w.p4["grid"] // data.STEP["1d"]
    last = np.r_[day[1:] != day[:-1], True]
    e = np.cumprod(1 + r)[last]
    return np.r_[e[0] - 1, e[1:] / e[:-1] - 1], year_of(w.p4["grid"][last]), w.p4["grid"][last]
