"""System 12 - the written hypotheses, tested in order by hyp12.py. Append only: never edit or delete one that ran.

Each entry says, BEFORE it runs, what it believes and why, and gives a small grid (the loop adds "off" and picks the
parameter on earlier years only). An overlay takes the book's 4h weights W (T x coins, + long / - short) and returns
new weights. Signals use closes up to bar t and are shifted with x.lag() so they trade from bar t+1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

D = 6  # 4h bars per day


@dataclass(frozen=True)
class H:
    id: str
    title: str
    text: str
    grid: tuple
    fn: Callable


def roll(x, n, f):
    return getattr(pd.Series(x).rolling(n, min_periods=max(2, n // 2)), f)().values


def latch(on: np.ndarray, off: np.ndarray) -> np.ndarray:
    """1 from a bar where `on` fires until a bar where `off` fires."""
    s, st = np.zeros(len(on)), 0.0
    for t in range(len(on)):
        if on[t]:
            st = 1.0
        elif off[t]:
            st = 0.0
        s[t] = st
    return s


def hold(fire: np.ndarray, k: int) -> np.ndarray:
    """1 for k bars after each bar where `fire` is true."""
    s, left = np.zeros(len(fire)), 0
    for t in range(len(fire)):
        left = k if fire[t] else max(0, left - 1)
        s[t] = 1.0 if left > 0 else 0.0
    return s


# ---------------------------------------------------------------- overlays

def crash_exit(x, W, p):
    dd = 1 - x.btc / roll(x.btc, 20 * D, "max")
    out = latch(dd > p, dd < p / 2)
    return x.scale_long(W, x.lag(1 - out))


def vol_break(x, W, p):
    r = np.r_[0, np.diff(np.log(x.btc))]
    fast, slow = roll(r, 7 * D, "std"), roll(r, 90 * D, "std")
    hot = np.nan_to_num(fast / slow) > p
    return x.scale_long(W, x.lag(np.where(hot, 0.5, 1.0)))


def fast_trend(x, W, p):
    ok = x.btc > roll(x.btc, p * D, "mean")
    return x.scale_long(W, x.lag(ok.astype(float)))


def short_size(x, W, p):
    return x.scale_short(W, np.full(x.T, p))


def long_size(x, W, p):
    return x.scale_long(W, np.full(x.T, p))


def eth_share(x, W, p):
    W = W.copy()
    b, e = np.maximum(W[:, x.ib], 0), np.maximum(W[:, x.ie], 0)
    tot = b + e
    both = (b > 0) & (e > 0)
    W[:, x.ib] = np.where(both, tot * (1 - p), W[:, x.ib])
    W[:, x.ie] = np.where(both, tot * p, W[:, x.ie])
    return W


def funding_crowd(x, W, p):
    f = np.nan_to_num(x.fund[:, x.ib])
    f7 = roll(f, 7 * D, "mean")
    q = pd.Series(f7).rolling(365 * D, min_periods=90 * D).quantile(p).values
    hot = np.isfinite(q) & (f7 > q)
    return x.scale_long(W, x.lag(np.where(hot, 0.5, 1.0)))


def _equity(x, W):
    return np.cumprod(1 + x.ret4(W))


def book_brake(x, W, p):
    eq = _equity(x, W)
    dd = 1 - eq / roll(eq, 60 * D, "max")
    return W * x.lag(np.where(dd > p, 0.5, 1.0))[:, None]


def book_stop(x, W, p):
    eq = _equity(x, W)
    r10 = eq / np.r_[np.full(10 * D, eq[0]), eq[:-10 * D]] - 1
    off = hold(r10 < -p, 5 * D)
    return W * x.lag(1 - off)[:, None]


def long_term_filter(x, W, p):
    ma = roll(x.btc, p * D, "mean")
    up = np.r_[np.zeros(10 * D), ma[10 * D:] > ma[:-10 * D]]
    return x.scale_long(W, x.lag(up.astype(float)))


def momentum_sizing(x, W, p):
    m30 = x.btc / np.r_[np.full(30 * D, x.btc[0]), x.btc[:-30 * D]] - 1
    return x.scale_long(W, x.lag(np.clip(np.nan_to_num(m30) / p, 0.5, 1.0)))


def short_below_200(x, W, p):
    ok = x.btc < roll(x.btc, p * D, "mean")
    return x.scale_short(W, x.lag(ok.astype(float)))


def short_cover(x, W, p):
    up = x.btc / roll(x.btc, 10 * D, "min") - 1
    cover = latch(up > p, up < p / 3)
    return x.scale_short(W, x.lag(1 - cover))


def ethbtc_switch(x, W, p):
    rr = x.eth / x.btc
    weak = rr < roll(rr, p * D, "mean")
    W = W.copy()
    b, e = W[:, x.ib], W[:, x.ie]
    mv = x.lag(weak.astype(float)) * (b > 0) * (e > 0)
    W[:, x.ib] = b + e * mv
    W[:, x.ie] = e * (1 - mv)
    return W


def band(x, W, p):
    out = W.copy()
    for t in range(1, len(W)):
        if np.abs(W[t] - out[t - 1]).sum() < p and np.abs(W[t]).sum() > 0:
            out[t] = out[t - 1]
    return out


def daily_only(x, W, p):
    day = (x.w.P4["grid"] // (86_400 * 10**9))
    first = np.r_[True, day[1:] != day[:-1]]
    idx = np.where(first, np.arange(len(W)), 0)
    np.maximum.accumulate(idx, out=idx)
    return W[idx] if p else W


def short_btc_only(x, W, p):
    W = W.copy()
    e = np.minimum(W[:, x.ie], 0)
    W[:, x.ib] = np.where(e < 0, W[:, x.ib] + e * p, W[:, x.ib])
    W[:, x.ie] = W[:, x.ie] - e * p
    return W


def day_crash(x, W, p):
    r1 = x.btc / np.r_[np.full(D, x.btc[0]), x.btc[:-D]] - 1
    off = hold(r1 < -p, 3 * D)
    return x.scale_long(W, x.lag(1 - off))


ALL = [
    H("H001", "Crash exit from the 20-day high",
      "The regime rules look 14-90 days back and leave late in a crash (2022: -23%). Exiting longs when BTC is X% below "
      "its 20-day high, and re-entering only when it recovers to X/2, should cut the crash years and cost little in bull years.",
      (0.10, 0.15, 0.20, 0.25), crash_exit),
    H("H002", "Volatility break halves longs",
      "Crashes start with a volatility burst. When BTC's 7-day volatility exceeds k times its 90-day volatility, halve the longs.",
      (1.5, 2.0, 2.5), vol_break),
    H("H003", "Fast trend guard",
      "Hold longs only while BTC is above its short moving average (N days); a faster exit than the 50-200-day regime.",
      (10, 20, 30), fast_trend),
    H("H004", "Short size",
      "The half-size short was the only size tested beyond 25/50/100%. Scaling the short leg changes the bear years most.",
      (0.5, 1.5, 2.0), short_size),
    H("H005", "Long size",
      "The 40% volatility target may be too cautious (invested 34-67%). Scale the long leg.",
      (0.75, 1.25, 1.5), long_size),
    H("H006", "ETH share of the long leg",
      "Equal BTC/ETH was never tested against other splits. ETH lagged BTC since 2022; a lower ETH share may help.",
      (0.0, 0.25, 0.75), eth_share),
    H("H007", "Crowded funding halves longs",
      "When BTC funding (7-day average) is above its trailing 1-year quantile q, longs are crowded and fragile: halve them.",
      (0.8, 0.9, 0.95), funding_crowd),
    H("H008", "Book drawdown brake",
      "When the book itself is X below its 60-day high, halve all exposure: losses cluster.",
      (0.08, 0.12, 0.16), book_brake),
    H("H009", "Book stop",
      "If the book lost more than X in 10 days, go flat for 5 days.",
      (0.05, 0.08, 0.12), book_stop),
    H("H010", "Long-term slope filter",
      "Longs only while BTC's N-day average is rising (vs 10 days ago): avoids buying bear-market rallies.",
      (100, 150, 200), long_term_filter),
    H("H011", "Momentum-strength sizing",
      "Scale longs by BTC's 30-day return / s, between 50% and 100%: full size only when the trend is strong.",
      (0.10, 0.20), momentum_sizing),
    H("H012", "Short only below the long average",
      "Short only while BTC is below its N-day average: avoids shorting corrections inside bull markets (2024).",
      (100, 150, 200), short_below_200),
    H("H013", "Short cover on a squeeze",
      "Cover shorts when BTC rises X above its 10-day low; re-short when it falls back.",
      (0.08, 0.12, 0.16), short_cover),
    H("H014", "ETH/BTC switch",
      "When ETH/BTC is below its N-day average, move the ETH long into BTC.",
      (30, 60, 90), ethbtc_switch),
    H("H015", "Rebalance band",
      "Skip rebalances smaller than a band of total weight: saves costs without changing the signal.",
      (0.05, 0.10, 0.20), band),
    H("H016", "Trade once a day",
      "Hold each day's first 4h decision for the whole day: less churn, same signal (the rules are daily).",
      (1,), daily_only),
    H("H017", "Short BTC instead of ETH",
      "Move the ETH short into BTC: ETH squeezes harder and costs more funding.",
      (0.5, 1.0), short_btc_only),
    H("H018", "One-day crash exit",
      "If BTC falls more than X in 24 hours, exit longs for 3 days.",
      (0.07, 0.10, 0.13), day_crash),
]


# ---------------------------------------------------------------- altcoins (operator 2026-10-21: "when BTC moves 50%,
# altcoins move 300%; find a formula that really profits from their volatility")

def _alt_long(x, W, share, basket, scale=1.0):
    """Move `share` (per bar) of the long leg into an altcoin basket, `scale` x its size."""
    L = np.maximum(W, 0).sum(axis=1)
    B = np.nan_to_num(x.eng.b4[basket])
    out = W - np.maximum(W, 0) * share[:, None] + B * (L * share * scale)[:, None]
    return np.where(x.eng.can, out, 0.0)


def _ret_n(y, n):
    return y / np.r_[np.full(n, y[0]), y[:-n]] - 1


def _alt_index(x):
    return np.cumprod(1 + np.nan_to_num(x.eng.bret["equal weight"]))


def _alt_lead(x, days):
    ai = x.eng.to4(_alt_index(x))
    return _ret_n(ai, days * D) - _ret_n(x.btc, days * D)


def alt_season(x, W, p):
    lead = _alt_lead(x, 30) > p
    return _alt_long(x, W, x.lag(lead.astype(float)), "5 strongest (90d)")


def alt_always(x, W, p):
    return _alt_long(x, W, np.full(x.T, p), "5 strongest (90d)")


def _breadth(x):
    c, m = x.close, x.w.P4["member"].astype(bool)
    ma = pd.DataFrame(c).rolling(50 * D, min_periods=25 * D).mean().values
    above = (c > ma) & m & np.isfinite(ma)
    return above.sum(axis=1) / np.maximum(m.sum(axis=1), 1)


def alt_breadth(x, W, p):
    return _alt_long(x, W, x.lag((_breadth(x) > p).astype(float)), "equal weight")


def alt_ethbtc(x, W, p):
    rr = x.eth / x.btc
    up = rr > roll(rr, p * D, "mean")
    return _alt_long(x, W, x.lag(up.astype(float)), "5 strongest (90d)")


def alt_short(x, W, p):
    S = np.maximum(-W, 0).sum(axis=1)
    B = np.nan_to_num(x.eng.b4["equal weight"])
    out = W + np.maximum(-W, 0) * p - B * (S * p)[:, None]
    return np.where(x.eng.can, out, 0.0)


def alt_season_big(x, W, p):
    lead = _alt_lead(x, 30) > 0.0
    return _alt_long(x, W, x.lag(lead.astype(float)), "5 strongest (90d)", p)


def alt_above_ma(x, W, p):
    lead = _alt_lead(x, p) > 0.0
    return _alt_long(x, W, x.lag(lead.astype(float)), "members above own 50d avg")


def alt_strong_regime(x, W, p):
    L = np.maximum(W, 0).sum(axis=1)
    full = L >= p - 1e-9
    lead = _alt_lead(x, 30) > 0.0
    return _alt_long(x, W, (full & x.lag(lead.astype(float)).astype(bool)).astype(float), "5 strongest (90d)")


ALL += [
    H("H019", "Alt season switch",
      "Altcoins move several times BTC, but only in alt seasons. When the equal-weight altcoin basket has beaten BTC by more "
      "than X over 30 days, move the long leg into the 5 strongest coins (90 days); otherwise stay in BTC+ETH.",
      (0.0, 0.10, 0.20), alt_season),
    H("H020", "Always part in the strongest alts",
      "A fixed share of the long leg always in the 5 strongest coins (90 days), to capture alt rallies whenever the regime is long.",
      (0.25, 0.50, 1.0), alt_always),
    H("H021", "Broad rally -> all coins",
      "When more than X of the top-14 coins are above their own 50-day average, the rally is broad and alts lead: "
      "move the long leg into the equal-weight basket.",
      (0.6, 0.7, 0.8), alt_breadth),
    H("H022", "ETH/BTC rising -> alts",
      "ETH/BTC above its N-day average is the classic alt-season signal: move the long leg into the 5 strongest coins.",
      (30, 60, 90), alt_ethbtc),
    H("H023", "Short altcoins in bear regimes",
      "Alts fall several times BTC in bear markets (-58% in 2022 vs BTC -64% only at the end). Move a share of the short leg "
      "from BTC/ETH into the equal-weight altcoin basket.",
      (0.5, 1.0), alt_short),
    H("H024", "Alt season with bigger size",
      "Same as H019 at X = 0, but the alt leg is p times the BTC+ETH size: the volatility target sized for BTC under-uses alts.",
      (1.0, 1.5, 2.0), alt_season_big),
    H("H025", "Alt lead over N days -> coins in their own uptrend",
      "When the alt basket beats BTC over N days, hold the coins that are above their own 50-day average.",
      (14, 30, 60), alt_above_ma),
    H("H026", "Alts only at full regime",
      "Move into the 5 strongest coins only when the regime is at full long size (at least p) AND alts lead BTC over 30 days.",
      (0.3, 0.4, 0.5), alt_strong_regime),
]


# ---------------------------------------------------------------- exposure (operator 2026-10-21: "average investment
# should always be above 80%; when we invest, increase the size of the positions")

def _gross(W):
    return np.abs(W).sum(axis=1)


def gross_target(x, W, p):
    g = _gross(W)
    k = np.where(g > 1e-9, p / np.maximum(g, 1e-9), 0.0)
    return W * k[:, None]


def vt_multiplier(x, W, p):
    g = _gross(W)
    k = np.minimum(p, 1.0 / np.maximum(g, 1e-9))
    return W * np.where(g > 1e-9, k, 0.0)[:, None]


def long_full(x, W, p):
    L = np.maximum(W, 0).sum(axis=1)
    k = np.where(L > 1e-9, p / np.maximum(L, 1e-9), 1.0)
    return x.scale_long(W, k)


def never_cash(x, W, p):
    g = _gross(W)
    W = W.copy()
    flat = g < 1e-9
    W[flat, x.ib] = p
    return np.where(x.eng.can, W, 0.0)


ALL += [
    H("H027", "Full size whenever in a position",
      "The volatility target keeps the book 34-67% invested. Whenever the book holds anything, scale the whole position "
      "(long or short) to p of capital: the signal decides direction, not size.",
      (0.8, 1.0, 1.2), gross_target),
    H("H028", "Higher volatility target",
      "Multiply every position by k (a higher volatility target), never above 100% gross.",
      (1.5, 2.0, 2.5), vt_multiplier),
    H("H029", "Full long leg",
      "When the regime is long, hold the long leg at p of capital; shorts unchanged.",
      (0.8, 1.0), long_full),
    H("H030", "Never in cash",
      "When the book is flat, hold BTC at p: average investment above 80% at all times.",
      (0.5, 0.8), never_cash),
]


# ---------------------------------------------------------------- the second layer (operator 2026-10-22: "a decision tree
# that corrects the buy/sell decisions; study every losing trade"). meta12.py builds hyp/meta_prob.npy and hyp/META.md.

def _meta_prob(x):
    from pathlib import Path
    p = np.load(Path(__file__).resolve().parent / "hyp" / "meta_prob.npy").astype(float)
    p = np.r_[p, np.full(max(0, x.T - len(p)), np.nan)][:x.T]
    return np.where(np.isfinite(p), p, 1.0)                      # no prediction = trust the signal


def meta_filter(x, W, p):
    thr, keep = p
    return W * x.lag(np.where(_meta_prob(x) < thr, keep, 1.0))[:, None]


def whipsaw_filter(x, W, p):
    ma50, ma200 = roll(x.btc, 50 * D, "mean"), roll(x.btc, 200 * D, "mean")
    rising = np.r_[np.zeros(10 * D), ma50[10 * D:] > ma50[:-10 * D]]
    ok = (x.btc > ma200 * (1 + p)) & (rising > 0)
    return x.scale_long(W, x.lag(ok.astype(float)))


def loss_cooldown(x, W, p):
    """After a long episode that lost money, ignore new long signals for p days."""
    L = np.maximum(W, 0).sum(axis=1)
    r = x.ret4(W)
    m, t, cool_until = np.ones(x.T), 0, -1
    while t < x.T:
        if L[t] <= 1e-9:
            t += 1
            continue
        a = t
        while t < x.T and L[t] > 1e-9:
            if t < cool_until:
                m[t] = 0.0
            t += 1
        if np.prod(1 + r[a:t]) - 1 < 0 and m[a:t].mean() > 0:
            cool_until = t + p * D
    return x.scale_long(W, m)


ALL += [
    H("H031", "Decision tree second layer",
      "A depth-3 tree, trained each year only on earlier years (RSI, averages, crosses, volatility, funding, breadth, ETH/BTC), "
      "estimates whether the position's direction is right over the next 7 days. Where it has no confidence (probability < thr) "
      "the position is cut to `keep`. Out-of-sample it separated well in 2021, 2022 and 2025, not in 2023-2024.",
      ((0.4, 0.5), (0.4, 0.0), (0.45, 0.5), (0.5, 0.5)), meta_filter),
    H("H032", "Whipsaw filter from the loser autopsy",
      "The losing longs (61% of trades, 2-18 days) enter with BTC barely above its 50-day average, that average falling and "
      "no support from the 200-day. Long only while BTC is more than p above its 200-day average AND the 50-day is rising. "
      "Derived from 2021-2025 trades: weaker evidence, the paper book is its real test.",
      (0.0, 0.03, 0.06), whipsaw_filter),
    H("H033", "Cooldown after a losing long",
      "Whipsaws come in series. After a long trade that lost money, ignore new long signals for p days.",
      (3, 7, 14), loss_cooldown),
]


# ---------------------------------------------------------------- the strategy catalogue (operator 2026-10-22: "locate the best
# published strategies, test them, keep them indexed"). Every catalogue strategy graded A or B on its own (catalog12.py) is
# combined with System 12 here, its walk-forward weights read from catalog/wf/<id>.npy. One hypothesis per strategy.

def _catalog_entries():
    import json
    from pathlib import Path
    cat = Path(__file__).resolve().parent / "catalog"
    if not (cat / "results.jsonl").exists():
        return []
    res = [json.loads(x) for x in (cat / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    names = {}
    for f in (cat / "raw").glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                s = json.loads(line)
                names[s["id"]] = s
            except Exception:  # noqa: BLE001
                pass
    good = sorted([r for r in res if r.get("tier") in ("A", "B") and (cat / "wf" / f"{r['id']}.npy").exists()],
                  key=lambda r: -r["ann"])
    return [(r, names.get(r["id"], {})) for r in good]


def _combine(sid):
    def fn(x, W, p):
        from pathlib import Path
        Ws = np.load(Path(__file__).resolve().parent / "catalog" / "wf" / f"{sid}.npy").astype(float)
        Ws = np.r_[Ws, np.zeros((max(0, x.T - len(Ws)), Ws.shape[1]))][:x.T]
        mode, a = p
        if mode == "blend":
            out = (1 - a) * W + a * Ws
        elif mode == "filter":
            out = x.scale_long(W, (np.maximum(Ws, 0).sum(axis=1) > 1e-9).astype(float))
        else:                                                         # add, gross capped at 100%
            out = W + Ws
            g = np.abs(out).sum(axis=1)
            out = out * np.minimum(1.0, 1.0 / np.maximum(g, 1e-9))[:, None]
        return np.where(x.eng.can, out, 0.0)
    return fn


for _i, (_r, _s) in enumerate(_catalog_entries()):
    ALL.append(H(f"K-{_r['id']}", f"System 12 + {_s.get('name', _r['id'])}"[:90],
                 f"Catalogue strategy {_r['id']} ({_s.get('source_url', '')}), grade {_r['tier']} on its own: "
                 f"2021-25 {_r['ann']:+.1%}/yr, DD {_r['dd']:.0%}. Combined with System 12: blended 25% or 50%, as a filter on "
                 f"System 12's longs, or added on top (gross <= 100%).",
                 (("blend", 0.25), ("blend", 0.5), ("filter", 1.0)), _combine(_r["id"])))   # v5: no "add" (it only stacked exposure)


# ---------------------------------------------------------------- the state before a signal (operator 2026-10-22: "the candles
# before a buy/sell signal - shape, range, volume, speed - may confirm or cancel it"). pre12.py: no single candle feature
# separates winners from losers after correction; a model on all of them ranked entries out of sample in 2021-23
# (AUC 0.58-0.65) and not in 2024-25 (0.50-0.52), but its trusted half earned more in all 5 years.

def _pre_prob(x, name):
    from pathlib import Path
    p = np.load(Path(__file__).resolve().parent / "pre" / f"{name}.npy").astype(float)
    p = np.r_[p, np.full(max(0, x.T - len(p)), np.nan)][:x.T]
    return np.where(np.isfinite(p), p, 1.0)


def pre_state_filter(x, W, p):
    """At the first bar of each long (short) trade of the book, read the model's P(win); below thr the whole trade is cut
    to `keep`. The probability for bar t uses candles up to t-1 and a model trained on earlier years only."""
    import gen12
    thr, keep = p
    pl, ps = _pre_prob(x, "prob_long"), _pre_prob(x, "prob_short")
    ml = gen12._episode_mult(x, W, +1, lambda s, c: s["k"] if s["n"] > 1 else (keep if pl[s["start"]] < thr else 1.0))
    ms = gen12._episode_mult(x, W, -1, lambda s, c: s["k"] if s["n"] > 1 else (keep if ps[s["start"]] < thr else 1.0))
    return x.scale_short(x.scale_long(W, ml), ms)


ALL += [
    H("H034", "The state before the signal",
      "The 4h candles before each trade (speed, acceleration, range and volume expansion, taker share, bodies, wicks, "
      "up-candle share, distance to the 30-day high/low, engulfing/hammer/star/inside bar) feed a regularised model trained "
      "on earlier years' entries; trades it does not trust (P(win) < thr) are cut to `keep`.",
      ((0.3, 0.5), (0.3, 0.0), (0.35, 0.5), (0.35, 0.0)), pre_state_filter),
]


# ---------------------------------------------------------------- task list (TODO.md) tasks 2-6 (operator 2026-10-22: "recognise
# bull, bear and sideways markets as early as possible and apply different criteria in each; know where we are in the cycle")

def _ext(x, name, daily=False):
    from pathlib import Path
    a = np.load(Path(__file__).resolve().parent / "ext" / f"{name}.npy").astype(float)
    if daily:
        return x.eng.to4(np.nan_to_num(a, nan=np.nan))
    return np.r_[a, np.zeros((max(0, x.T - len(a)),) + a.shape[1:])][:x.T]


def _er(x, n):
    """Kaufman efficiency ratio of BTC over n days: 1 = straight line, 0 = pure chop."""
    c = x.btc
    k = n * D
    net = np.abs(c - np.r_[np.full(k, c[0]), c[:-k]])
    path = roll(np.abs(np.r_[0, np.diff(c)]), k, "sum")
    return np.nan_to_num(net / np.maximum(path, 1e-9))


def phase_switch(x, W, p):
    """Sideways = efficiency ratio below thr. There: `flat` (no position), `mr` (the catalogue's mean-reversion average
    instead of the trend book), or `half` (trend book at half size)."""
    n, thr, act = p
    side = x.lag((_er(x, n) < thr).astype(float))[:, None]
    if act == "flat":
        alt = np.zeros_like(W)
    elif act == "half":
        alt = 0.5 * W
    else:
        alt = _ext(x, "ens_mr")
    return np.where(x.eng.can, W * (1 - side) + alt * side, 0.0)


def cycle_size(x, W, p):
    """Where we are in the cycle: Mayer multiple (BTC / 200-day average) above hi -> longs x0.5 (late, euphoric);
    more than dd below the all-time high -> longs x1.25 (deep, early)."""
    hi, dd = p
    mayer = x.btc / roll(x.btc, 200 * D, "mean")
    ath = 1 - x.btc / np.maximum.accumulate(np.nan_to_num(x.btc))
    m = np.where(np.nan_to_num(mayer) > hi, 0.5, np.where(ath > dd, 1.25, 1.0))
    return gen12_cap(x.scale_long(W, x.lag(m)))


def gen12_cap(W):
    g = np.abs(W).sum(axis=1)
    return W * np.minimum(1.0, 1.0 / np.maximum(g, 1e-9))[:, None]


def mvrv_trim(x, W, p):
    m = _ext(x, "mvrv", daily=True)
    return x.scale_long(W, np.where(np.nan_to_num(m) > p, 0.5, 1.0))


def mvrv_value(x, W, p):
    """MVRV below p (price under the average holder's cost) and BTC above its 50-day average: long even if the regime
    still says bear - the early-cycle entry the 50-200-day rules give late."""
    lo, size = p
    m = _ext(x, "mvrv", daily=True)
    ok = (np.nan_to_num(m, nan=9) < lo) & x.lag((x.btc > roll(x.btc, 50 * D, "mean")).astype(float)).astype(bool)
    W = W.copy()
    flat = np.abs(W).sum(axis=1) < 1e-9
    put = ok & flat
    W[put, x.ib] = size / 2
    W[put, x.ie] = size / 2
    return np.where(x.eng.can, W, 0.0)


def dvol_fear(x, W, p):
    v = _ext(x, "dvol", daily=True)
    q = HY_pd.Series(v).rolling(365 * D, min_periods=120 * D).quantile(p).values
    hot = np.isfinite(q) & (np.nan_to_num(v) > q)
    return x.scale_long(W, np.where(hot, 0.5, 1.0))


import pandas as HY_pd  # noqa: E402


def ensemble_blend(x, W, p):
    name, a = p
    E = _ext(x, f"ens_{name}")
    return np.where(x.eng.can, (1 - a) * W + a * E, 0.0)


def coins_blend(x, W, p):
    n, a = p
    E = _ext(x, f"coins_{n}")
    return np.where(x.eng.can, (1 - a) * W + a * E, 0.0)


ALL += [
    H("H035", "Market phases: sideways markets",
      "System 12 only knows up and down; in sideways markets its trend rules whipsaw (61% of trades lose, most in flat "
      "markets). When BTC's efficiency ratio over n days is below thr the market is sideways: go flat, halve, or switch "
      "to the catalogue's mean-reversion average.",
      ((20, 0.15, "flat"), (20, 0.15, "mr"), (20, 0.15, "half"), (30, 0.2, "flat"), (30, 0.2, "mr"), (30, 0.2, "half"),
       (60, 0.15, "mr"), (60, 0.15, "flat")), phase_switch),
    H("H036", "Cycle position sizing",
      "Crypto is cyclical. Late in a cycle (Mayer multiple above hi) halve longs; deep in a drawdown (more than dd below "
      "the all-time high) size longs up 25%.",
      ((2.0, 0.6), (2.4, 0.6), (2.0, 0.75), (2.4, 0.75)), cycle_size),
    H("H037", "MVRV late-cycle trim",
      "On-chain: MVRV (market value / realised value) above p marks euphoric tops; halve longs there.",
      (2.5, 3.0, 3.5), mvrv_trim),
    H("H038", "MVRV early-cycle entry",
      "MVRV below lo (price under holders' average cost) with BTC back above its 50-day average: be long at `size` while "
      "the slow regime rules are still flat - the cycle bottom the 50-200-day rules catch late.",
      ((1.0, 0.5), (1.2, 0.5), (1.0, 1.0), (1.2, 1.0)), mvrv_value),
    H("H039", "Implied volatility fear",
      "Deribit DVOL above its trailing 1-year quantile p = fear; halve longs (data from 2021-04).",
      (0.8, 0.9, 0.95), dvol_fear),
    H("H040", "Average of the catalogue's A/B strategies",
      "Averaging many decent published rules rarely overfits. Blend System 12 with the average of the catalogue's A/B "
      "strategies: all of them, trend family, or macro/crypto/calendar family.",
      (("all", 0.25), ("all", 0.5), ("all", 0.75), ("trend", 0.25), ("trend", 0.5), ("other", 0.25), ("other", 0.5)),
      ensemble_blend),
    H("H041", "Trend on the top-14 coins",
      "More independent bets: breakout trend on each coin of the point-in-time top 14 (Zarattini et al. 2025), "
      "volatility-targeted, blended with System 12.",
      ((10, 0.25), (20, 0.25), (40, 0.25), (20, 0.5), (40, 0.5)), coins_blend),
]


# ---------------------------------------------------------------- task 12: the liquidity family. Written after task 11 showed the
# net-liquidity z-spread failed 2014-2020, so these are simpler, slower liquidity measures. Each must also pass the
# 2014-2020 gate (gate13-style) before it can become champion.

def m2_filter(x, W, p):
    """Longs at full size only while US M2 grew over the last p days (published-date lag already applied); else half."""
    m = _ext(x, "m2", daily=True)
    k = p * D
    g = m / np.r_[np.full(k, np.nan), m[:-k]] - 1
    return x.scale_long(W, np.where(np.nan_to_num(g, nan=1) > 0, 1.0, 0.5))


def stables_filter(x, W, p):
    """Longs at full size only while total stablecoin supply grew over p days (dry powder entering crypto); else half."""
    s = _ext(x, "stables", daily=True)
    k = p * D
    g = s / np.r_[np.full(k, np.nan), s[:-k]] - 1
    return x.scale_long(W, np.where(np.nan_to_num(g, nan=1) > 0, 1.0, 0.5))


def netliq_momentum(x, W, p):
    """Longs at full size only while Fed net liquidity rose over p days; else half."""
    import catalog12 as C  # noqa: F401  (netliq comes from the macro cache via the catalogue's Book)
    from pathlib import Path
    f = Path(__file__).resolve().parent / "ext" / "netliq.npy"
    if not f.exists():
        b = C.Book()
        np.save(f, b.common["netliq"].values.astype(np.float32))
    n = x.eng.to4(np.load(f).astype(float))
    k = p * D
    g = n - np.r_[np.full(k, np.nan), n[:-k]]
    return x.scale_long(W, np.where(np.nan_to_num(g, nan=1) > 0, 1.0, 0.5))


ALL += [
    H("H042", "M2 growth", "Global liquidity drives crypto (Hayes, Raoul Pal). Hold longs at full size only while US M2 grew "
      "over the last p days (published ~4 weeks late: lagged 55 days); otherwise half.", (90, 180, 365), m2_filter),
    H("H043", "Stablecoin supply growth", "Stablecoins are crypto's own cash: growing supply = buying power arriving. Full "
      "longs only while total stablecoin supply grew over p days; otherwise half.", (30, 60, 90), stables_filter),
    H("H044", "Net liquidity momentum", "Simpler than the z-spread that failed 2014-2020: full longs only while Fed net "
      "liquidity (balance sheet - TGA - RRP) rose over p days; otherwise half.", (30, 60, 120), netliq_momentum),
]
