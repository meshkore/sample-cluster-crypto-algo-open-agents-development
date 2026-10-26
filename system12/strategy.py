"""The strategy: from market data to target weights on BTC and ETH.

    regime signals (daily, 0..1)  ->  20 frozen members (long leg, short leg, volatility target)
                                  ->  average  ->  overlays (short trail, convex trend sizing)  ->  weights

Row t of the weights is decided at the close of 4h bar t and held until t+1. Daily signals are read at the last daily
close before the decision. The rules are deterministic: no seeds, no fitted parameters. The members and overlay
parameters are frozen in selection.json (see docs/ARCHITECTURE.md for how they were chosen).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BARS_PER_DAY, SELECTION
from .market import Market

BASKETS = {"BTC": (1.0, 0.0), "BTC+ETH": (0.5, 0.5)}


# ------------------------------------------------------------------ regime signals


def signals(m: Market) -> dict[str, np.ndarray]:
    """BTC trend readings on the daily grid, each 0 or 1 (the ensembles are averages)."""
    btc = pd.Series(m.close1[:, 0])

    def ma(n: int) -> pd.Series:
        return btc.rolling(n, min_periods=n).mean()

    out = {f"BTC>MA{n}": (btc > ma(n)).values.astype(float) for n in (20, 50, 100, 150, 200)}
    out["BTC MA ensemble 20/50/100/200"] = np.mean([out[f"BTC>MA{n}"] for n in (20, 50, 100, 200)], axis=0)
    out["BTC MA-ratio rules (Detzel)"] = np.mean(
        [(ma(fast) > ma(slow)).values for fast in (5, 10, 20) for slow in (50, 100, 200)], axis=0
    ).astype(float)
    for n in (14, 30, 60):
        out[f"BTC {n}d momentum"] = (btc / btc.shift(n) > 1).values.astype(float)
    return {k: np.nan_to_num(v) for k, v in out.items()}


def regime(sig: dict[str, np.ndarray], name: str) -> np.ndarray:
    """'A AND B' is the minimum of two signals, 'mean(A | B)' their average, anything else a single signal."""
    if name.startswith("mean("):
        a, b = name[5:-1].split(" | ")
        return (sig[a] + sig[b]) / 2
    if " AND " in name:
        a, b = name.split(" AND ")
        return np.minimum(sig[a], sig[b])
    return sig[name]


# ------------------------------------------------------------------ the members


def _quarters(x: np.ndarray) -> np.ndarray:
    """Exposure in steps of 25%, so the book does not trade on every small change."""
    return np.floor(x * 4 + 1e-9) / 4


class Members:
    """Turns one member's regime reading into 4h weights: long basket, volatility target, optional short leg."""

    def __init__(self, m: Market):
        self.m = m
        r1 = np.nan_to_num(m.close1[1:] / m.close1[:-1] - 1)
        r1 = np.r_[np.zeros((1, r1.shape[1])), r1]
        self.daily_ret = {k: r1 @ np.array(w) for k, w in BASKETS.items()}
        self.live = np.isfinite(m.close4)
        self.basket4 = {k: self._basket4(np.array(w)) for k, w in BASKETS.items()}

    def to_4h(self, daily: np.ndarray) -> np.ndarray:
        """Daily series -> 4h bars, using the last daily close before each decision."""
        out = daily[np.clip(self.m.day_of_bar, 0, None)].copy()
        out[self.m.day_of_bar < 0] = 0.0
        return out

    def _basket4(self, w: np.ndarray) -> np.ndarray:
        W = np.where(self.live, np.tile(w, (len(self.m.grid4), 1)), 0.0)
        W[self.m.day_of_bar < 0] = 0.0
        s = W.sum(axis=1, keepdims=True)
        return np.where(s > 1.0, W / np.maximum(s, 1e-12), W)

    def _vol(self, basket: str) -> np.ndarray:
        return pd.Series(self.daily_ret[basket]).rolling(30, min_periods=20).std().values * np.sqrt(365)

    def long_exposure(self, reg: np.ndarray, basket: str, vol_target: float) -> np.ndarray:
        e = reg.copy()
        if vol_target:
            vol = self._vol(basket)
            e = e * np.clip(vol_target / np.where(np.isfinite(vol) & (vol > 0), vol, np.inf), 0, 1)
            e = np.where(np.isfinite(vol), e, 0.0)
        return _quarters(e)

    def vol_scale(self, basket: str, vol_target: float) -> np.ndarray:
        if not vol_target:
            return np.ones(len(self.m.grid1))
        vol = self._vol(basket)
        return np.where(np.isfinite(vol) & (vol > 0), np.clip(vol_target / np.where(vol > 0, vol, 1), 0, 1), 0.0)

    def weights(self, reg: np.ndarray, basket: str, vol_target: float, short: tuple | None) -> np.ndarray:
        W = self.basket4[basket] * self.to_4h(self.long_exposure(reg, basket, vol_target))[:, None]
        if short:
            short_basket, threshold, size = short
            bear = np.where(reg <= threshold + 1e-9, 1.0 - reg, 0.0) * size * self.vol_scale(short_basket, vol_target)
            W = W - self.basket4[short_basket] * self.to_4h(_quarters(bear))[:, None]
        return np.where(self.m.tradable, W, 0.0)


def base_weights(m: Market) -> np.ndarray:
    """The average of the frozen members."""
    members, sig = Members(m), signals(m)
    rows = SELECTION["members"]
    total = sum(
        members.weights(regime(sig, reg), basket, float(vt), tuple(short) if short else None) for reg, basket, vt, short in rows
    )
    return total / len(rows)


# ------------------------------------------------------------------ overlays


def _ffill(x: np.ndarray) -> np.ndarray:
    idx = np.where(np.isfinite(x), np.arange(len(x)), 0)
    np.maximum.accumulate(idx, out=idx)
    return x.astype(float)[idx]


def _lag(x: np.ndarray) -> np.ndarray:
    """Shift by one bar: a multiplier computed at close t applies from t+1."""
    return np.r_[x[:1], x[:-1]].astype(float)


def _cap_gross(W: np.ndarray, cap: float = 1.0) -> np.ndarray:
    gross = np.abs(W).sum(axis=1)
    return W * np.minimum(1.0, cap / np.maximum(gross, 1e-9))[:, None]


def trail_short(btc: np.ndarray, W: np.ndarray, p: float) -> np.ndarray:
    """Inside each short episode, cover once BTC closes more than p above its lowest close since the episode began."""
    short_on = np.maximum(-W, 0).sum(axis=1) > 1e-9
    keep, active, k, low = np.ones(len(W)), False, 1.0, np.nan
    for t in range(len(W)):
        if not short_on[t]:
            active = False
            continue
        if not active:
            active, k, low = True, 1.0, btc[t]
        low = min(low, btc[t])
        k = 0.0 if k == 0 or btc[t] > low * (1 + p) else 1.0  # once covered, stays covered until the episode ends
        keep[t] = k
    keep = _lag(keep)
    return np.where(W < 0, W * keep[:, None], W)


def trend_convex(btc: np.ndarray, W: np.ndarray, p: float) -> np.ndarray:
    """Long leg x clip(1 + BTC 30-day return / p, 0.5, 2), then gross exposure capped at 100%."""
    lag30 = 30 * BARS_PER_DAY
    ret30 = btc / np.r_[np.full(lag30, btc[0]), btc[:-lag30]] - 1
    mult = _lag(np.clip(1 + np.nan_to_num(ret30) / p, 0.5, 2.0))
    return _cap_gross(np.where(W > 0, W * mult[:, None], W))


OVERLAYS = {"trail_short": trail_short, "trend_convex": trend_convex}


def target_weights(m: Market) -> np.ndarray:
    """The executed target weights, shape (4h bars, coins)."""
    W = base_weights(m)
    btc = _ffill(m.close4[:, 0])
    for name, p in SELECTION["overlays"]:
        W = OVERLAYS[name](btc, W, float(p))
    return W
