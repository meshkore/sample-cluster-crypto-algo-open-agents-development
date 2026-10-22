"""System 12 - the hypothesis GENERATOR (operator 2026-10-21: "keep developing this while I sleep - entries, exits,
stop-loss, take-profit, size, crazy ideas, combine all the hypotheses").

When the written queue (hypotheses12.py) is empty, hyp12.py asks this module for the next batch. A generated hypothesis is
a stack of 1-3 PIECES from the catalogue below; its text is written from the pieces' texts and stored in
hyp/generated.jsonl BEFORE it runs, so the ledger can rebuild it. Order of work:
    1. every piece alone,  2. every pair,  3. random triples, forever.
Pairs and triples are sampled with a bias toward pieces whose tests have helped so far (a simple bandit), so the search
leans where the evidence points. The judge is unchanged (hyp12.py): walk-forward, a bar that rises with every test,
2026 never used.
"""

from __future__ import annotations

import itertools
import json
import math
import random
from pathlib import Path

import numpy as np

import hypotheses12 as HY
from hypotheses12 import D, H, hold, latch, roll

GEN = Path(__file__).resolve().parent / "hyp" / "generated.jsonl"


# ---------------------------------------------------------------- episode helpers (a long or short "trade" of the book)

def _episodes(on: np.ndarray) -> np.ndarray:
    """Episode start index for every bar inside an episode, -1 outside."""
    st, out = -1, np.full(len(on), -1)
    for t in range(len(on)):
        if on[t]:
            st = t if st < 0 else st
            out[t] = st
        else:
            st = -1
    return out


def _cap(W, g=1.0):
    gross = np.abs(W).sum(axis=1)
    return W * np.minimum(1.0, g / np.maximum(gross, 1e-9))[:, None]


def _episode_mult(x, W, side, rule):
    """Run `rule(state)` inside each long (side=+1) or short (side=-1) episode of W; returns a per-bar multiplier."""
    leg = np.maximum(W, 0).sum(axis=1) if side > 0 else np.maximum(-W, 0).sum(axis=1)
    ep = _episodes(leg > 1e-9)
    m, px = np.ones(x.T), x.btc
    st = None
    for t in range(x.T):
        if ep[t] < 0:
            st = None
            continue
        if st is None or st["start"] != ep[t]:
            st = {"start": ep[t], "entry": px[t], "hi": px[t], "lo": px[t], "k": 1.0, "n": 0}
        st["hi"], st["lo"], st["n"] = max(st["hi"], px[t]), min(st["lo"], px[t]), st["n"] + 1
        st["k"] = rule(st, px[t])
        m[t] = st["k"]
    return x.lag(m)


# ---------------------------------------------------------------- new pieces: entries, exits, stops, take-profits, sizing

def trail_long(x, W, p):
    m = _episode_mult(x, W, +1, lambda s, c: 0.0 if s["k"] == 0 or c < s["hi"] * (1 - p) else 1.0)
    return x.scale_long(W, m)


def stop_long(x, W, p):
    m = _episode_mult(x, W, +1, lambda s, c: 0.0 if s["k"] == 0 or c < s["entry"] * (1 - p) else 1.0)
    return x.scale_long(W, m)


def tp_long(x, W, p):
    m = _episode_mult(x, W, +1, lambda s, c: 0.5 if s["k"] == 0.5 or c > s["entry"] * (1 + p) else 1.0)
    return x.scale_long(W, m)


def pyramid_long(x, W, p):
    m = _episode_mult(x, W, +1, lambda s, c: 1.5 if s["k"] == 1.5 or c > s["entry"] * (1 + p) else 1.0)
    return _cap(x.scale_long(W, m))


def time_exit_long(x, W, p):
    m = _episode_mult(x, W, +1, lambda s, c: 0.0 if s["n"] > p * D else 1.0)
    return x.scale_long(W, m)


def entry_delay(x, W, p):
    m = _episode_mult(x, W, +1, lambda s, c: 0.0 if s["n"] <= p * D else 1.0)
    return x.scale_long(W, m)


def entry_confirm(x, W, p):
    m = _episode_mult(x, W, +1, lambda s, c: 1.0 if s["k"] == 1.0 or c > s["entry"] * (1 + p) else 0.0)
    return x.scale_long(W, m)


def trail_short(x, W, p):
    m = _episode_mult(x, W, -1, lambda s, c: 0.0 if s["k"] == 0 or c > s["lo"] * (1 + p) else 1.0)
    return x.scale_short(W, m)


def stop_short(x, W, p):
    m = _episode_mult(x, W, -1, lambda s, c: 0.0 if s["k"] == 0 or c > s["entry"] * (1 + p) else 1.0)
    return x.scale_short(W, m)


def tp_short(x, W, p):
    m = _episode_mult(x, W, -1, lambda s, c: 0.5 if s["k"] == 0.5 or c < s["entry"] * (1 - p) else 1.0)
    return x.scale_short(W, m)


def breakout_boost(x, W, p):
    hi = x.btc >= roll(x.btc, p * D, "max") * 0.999
    return _cap(x.scale_long(W, x.lag(np.where(hi, 1.5, 1.0))))


def dip_boost(x, W, p):
    dd = 1 - x.btc / roll(x.btc, 30 * D, "max")
    return _cap(x.scale_long(W, x.lag(np.where((dd > p) & (dd < 2 * p), 1.5, 1.0))))


def trend_convex(x, W, p):
    m30 = x.btc / np.r_[np.full(30 * D, x.btc[0]), x.btc[:-30 * D]] - 1
    return _cap(x.scale_long(W, x.lag(np.clip(1 + np.nan_to_num(m30) / p, 0.5, 2.0))))


def vol_inverse(x, W, p):
    r = np.r_[0, np.diff(np.log(x.btc))]
    v = roll(r, 14 * D, "std") * math.sqrt(365 * D)
    return _cap(W * x.lag(np.clip(p / np.maximum(np.nan_to_num(v, nan=1), 1e-3), 0.25, 2.0))[:, None])


def recent_edge(x, W, p):
    r = x.ret4(W)
    s = roll(r, p * D, "mean")
    return W * x.lag(np.where(np.nan_to_num(s) < 0, 0.5, 1.0))[:, None]


def gross_cap(x, W, p):
    return _cap(W * 2.0, p)


def weekend_flat(x, W, p):
    dow = ((x.w.P4["grid"] // (86_400 * 10**9)) + 3) % 7          # 0 = Monday
    return W * np.where(dow >= 5, p, 1.0)[:, None]


# ---------------------------------------------------------------- the catalogue: (key, family, text, grid, fn)

PIECES = [
    ("trail_long", "exit", "trailing stop on longs: out when BTC falls p below its high since entry, back at the next long episode", (0.08, 0.12, 0.18, 0.25), trail_long),
    ("stop_long", "stop-loss", "stop-loss on longs: out when BTC is p below the entry price", (0.05, 0.08, 0.12, 0.18), stop_long),
    ("tp_long", "take-profit", "take-profit: halve longs once BTC is p above entry", (0.15, 0.30, 0.50, 0.80), tp_long),
    ("pyramid_long", "size", "pyramiding: longs x1.5 once BTC is p above entry (gross <= 100%)", (0.05, 0.10, 0.20), pyramid_long),
    ("time_exit_long", "exit", "time exit: longs out after p days in the episode", (30, 60, 120), time_exit_long),
    ("entry_delay", "entry", "entry delay: ignore the first p days of a long episode (false starts)", (1, 3, 7), entry_delay),
    ("entry_confirm", "entry", "entry confirmation: buy only once BTC is p above the episode's first price", (0.02, 0.05, 0.10), entry_confirm),
    ("trail_short", "exit", "trailing stop on shorts: cover when BTC rises p above its low since entry", (0.06, 0.10, 0.15), trail_short),
    ("stop_short", "stop-loss", "stop-loss on shorts: cover when BTC is p above the short entry", (0.05, 0.08, 0.12), stop_short),
    ("tp_short", "take-profit", "take-profit on shorts: halve once BTC is p below entry", (0.10, 0.20, 0.35), tp_short),
    ("breakout_boost", "entry", "breakout: longs x1.5 while BTC is at its p-day high", (20, 55, 100), breakout_boost),
    ("dip_boost", "entry", "buy the dip: longs x1.5 when BTC is between p and 2p below its 30-day high", (0.05, 0.08, 0.12), dip_boost),
    ("trend_convex", "size", "convex sizing: longs x(1 + 30d BTC return / p), between 0.5 and 2", (0.2, 0.4, 0.8), trend_convex),
    ("vol_inverse", "size", "inverse-volatility sizing on BTC 14d vol, target p", (0.4, 0.6, 0.8), vol_inverse),
    ("recent_edge", "size", "halve the book while its own p-day mean return is negative", (10, 20, 40), recent_edge),
    ("gross_cap", "size", "double every position, gross capped at p", (0.8, 1.0, 1.2), gross_cap),
    ("weekend_flat", "crazy", "weekends at p of size (thin books, wicks)", (0.0, 0.5), weekend_flat),
    # the written hypotheses' overlays, reused as pieces
    ("crash_exit", "exit", "exit longs p below BTC's 20-day high", (0.10, 0.15, 0.20, 0.25), HY.crash_exit),
    ("vol_break", "exit", "halve longs when 7d vol > p x 90d vol", (1.5, 2.0, 2.5), HY.vol_break),
    ("fast_trend", "exit", "longs only above BTC's p-day average", (10, 20, 30), HY.fast_trend),
    ("short_size", "size", "short leg x p", (0.5, 1.5, 2.0), HY.short_size),
    ("long_size", "size", "long leg x p", (0.75, 1.25, 1.5), HY.long_size),
    ("eth_share", "basket", "ETH share p of the long leg", (0.0, 0.25, 0.75), HY.eth_share),
    ("funding_crowd", "exit", "halve longs when funding > its 1y quantile p", (0.8, 0.9, 0.95), HY.funding_crowd),
    ("book_brake", "stop-loss", "halve the book p below its 60-day high", (0.08, 0.12, 0.16), HY.book_brake),
    ("long_term_filter", "entry", "longs only while BTC's p-day average rises", (100, 150, 200), HY.long_term_filter),
    ("short_below", "entry", "short only below BTC's p-day average", (100, 150, 200), HY.short_below_200),
    ("short_cover", "exit", "cover shorts p above BTC's 10-day low", (0.08, 0.12, 0.16), HY.short_cover),
    ("alt_season", "alts", "alts (5 strongest) when they beat BTC by p over 30 days", (0.0, 0.10, 0.20), HY.alt_season),
    ("alt_short", "alts", "share p of the short leg in the altcoin basket", (0.5, 1.0), HY.alt_short),
    ("vt_mult", "size", "every position x p, gross <= 100%", (1.25, 1.5, 2.0), HY.vt_multiplier),
    ("day_crash", "exit", "longs out 3 days after a 24h BTC drop of p", (0.07, 0.10, 0.13), HY.day_crash),
]
BY = {p[0]: p for p in PIECES}
MAX_GRID = 27


def make(gid: str, keys: list[str]) -> H:
    ps = [BY[k] for k in keys]
    grids = [p[3] for p in ps]
    combos = list(itertools.product(*grids))
    if len(combos) > MAX_GRID:                                       # keep the per-year choice small (less luck)
        rng = random.Random(gid)
        combos = rng.sample(combos, MAX_GRID)
    fns = [p[4] for p in ps]

    def fn(x, W, p, fns=fns):
        for f, q in zip(fns, p):
            W = f(x, W, q)
        return W

    text = "Generated. " + " THEN ".join(p[2] for p in ps) + "."
    title = " + ".join(k for k in keys)
    return H(gid, title, text, tuple(combos), fn)


def load() -> list[H]:
    if not GEN.exists():
        return []
    return [make(e["id"], e["keys"]) for e in (json.loads(x) for x in GEN.read_text(encoding="utf-8").splitlines() if x.strip())]


def _scores(ledger: list) -> dict:
    """Mean gain per piece over the generated tests that used it (the bandit's evidence)."""
    gen = {}
    if GEN.exists():
        gen = {e["id"]: e["keys"] for e in (json.loads(x) for x in GEN.read_text(encoding="utf-8").splitlines() if x.strip())}
    acc = {k: [] for k in BY}
    for e in ledger:
        for k in gen.get(e["id"], []):
            # score what can be ADOPTED: a gain bought with extra drawdown is not a gain under the rule
            pen = max(0.0, (e.get("dd", 0) or 0) - 0.40)                      # the operator's cap (2026-10-22)
            acc[k].append((e.get("mean_gain", 0) or 0) - pen)
    return {k: (float(np.mean(v)) if v else 0.0, len(v)) for k, v in acc.items()}


def next_batch(ledger: list, n: int = 10) -> list[H]:
    GEN.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if GEN.exists():
        done = {tuple(json.loads(x)["keys"]) for x in GEN.read_text(encoding="utf-8").splitlines() if x.strip()}
    count = len(done)
    want = []
    singles = [(k,) for k in BY]
    pairs = [c for c in itertools.combinations(BY, 2)]
    for c in singles + pairs:
        if c not in done and c not in want:
            want.append(c)
        if len(want) >= n:
            break
    if len(want) < n:                                               # triples, biased toward pieces that helped
        sc = _scores(ledger)
        keys = list(BY)
        # softened bandit (2026-10-22): exp(40 x gain) let two pieces take all the weight, no distinct triple could be
        # drawn and the loop idled all night. Clipped scores, a floor, and draws without replacement.
        w = np.array([math.exp(10 * min(max(sc[k][0], -0.1), 0.1)) for k in keys])
        w = np.maximum(w / w.sum(), 0.2 / len(keys))
        w = w / w.sum()
        rng = np.random.default_rng(count)
        tries = 0
        while len(want) < n and tries < 5000:
            tries += 1
            pick = tuple(sorted(rng.choice(len(keys), size=3, replace=False, p=w)))
            c = tuple(keys[i] for i in pick)
            if c not in done and c not in want:
                want.append(c)
    out = []
    with GEN.open("a", encoding="utf-8") as fh:
        for i, c in enumerate(want):
            gid = f"G{count + i + 1:05d}"
            fh.write(json.dumps({"id": gid, "keys": list(c)}) + "\n")
            out.append(make(gid, list(c)))
    return out


# ---------------------------------------------------------------- batch 2 (2026-10-22, operator "go"): more entries, exits and
# sizes, and moderate size steps that can fit under the 40% drawdown cap

def _rsi(c, n):
    d = np.r_[0, np.diff(c)]
    up, dn = roll(np.maximum(d, 0), n, "mean"), roll(np.maximum(-d, 0), n, "mean")
    return 100 - 100 / (1 + np.nan_to_num(up / np.maximum(dn, 1e-12), nan=1.0))


def _atr_pct(x, n):
    r = np.abs(np.r_[0, np.diff(np.log(x.btc))])
    return roll(r, n, "mean") * D                                  # ~ daily range as a fraction of price


def atr_trail_long(x, W, p):
    a = _atr_pct(x, 14 * D)
    m = _episode_mult(x, W, +1, lambda s, c: 0.0 if s["k"] == 0 or c < s["hi"] * (1 - p * a[min(s["start"] + s["n"] - 1, x.T - 1)]) else 1.0)
    return x.scale_long(W, m)


def ma_cross_exit(x, W, p):
    fast, slow = roll(x.btc, p[0] * D, "mean"), roll(x.btc, p[1] * D, "mean")
    return x.scale_long(W, x.lag((fast >= slow).astype(float)))


def rsi_trim(x, W, p):
    r = _rsi(x.btc, 14 * D)
    return x.scale_long(W, x.lag(np.where(r > p, 0.5, 1.0)))


def rsi_cover(x, W, p):
    r = _rsi(x.btc, 14 * D)
    return x.scale_short(W, x.lag(np.where(r < p, 0.0, 1.0)))


def neg_funding_boost(x, W, p):
    f7 = roll(np.nan_to_num(x.fund[:, x.ib]), 7 * D, "mean")
    return _cap(x.scale_long(W, x.lag(np.where(f7 < 0, p, 1.0))))


def calm_leverage(x, W, p):
    r = np.r_[0, np.diff(np.log(x.btc))]
    v30 = roll(r, 30 * D, "std")
    med = HY.pd.Series(v30).rolling(365 * D, min_periods=90 * D).median().values
    calm = np.isfinite(med) & (v30 < med)
    return _cap(x.scale_long(W, x.lag(np.where(calm, p, 1.0))))


def ramp_up(x, W, p):
    m = _episode_mult(x, W, +1, lambda s, c: min(1.5, 0.5 + s["n"] / (p * D)))
    return _cap(x.scale_long(W, m))


def dd_adaptive(x, W, p):
    eq = np.cumprod(1 + x.ret4(W))
    dd = 1 - eq / np.maximum.accumulate(eq)
    return W * x.lag(np.clip(1 - dd / p, 0.25, 1.0))[:, None]


def eth_trend_confirm(x, W, p):
    ok = x.eth > roll(x.eth, p * D, "mean")
    return x.scale_long(W, x.lag(np.where(ok, 1.0, 0.5)))


def september_light(x, W, p):
    month = (x.w.P4["grid"].astype("datetime64[ns]").astype("datetime64[M]").astype(int) % 12) + 1
    return W * np.where(month == 9, p, 1.0)[:, None]


def short_weaker(x, W, p):
    rb, re = (x.btc / np.r_[np.full(p * D, x.btc[0]), x.btc[:-p * D]]), (x.eth / np.r_[np.full(p * D, x.eth[0]), x.eth[:-p * D]])
    W = W.copy()
    sb, se = np.minimum(W[:, x.ib], 0), np.minimum(W[:, x.ie], 0)
    tot = sb + se
    eth_weaker = x.lag((re < rb).astype(float)).astype(bool)
    W[:, x.ib] = np.where(tot < 0, np.where(eth_weaker, np.maximum(W[:, x.ib], 0), np.maximum(W[:, x.ib], 0) + tot), W[:, x.ib])
    W[:, x.ie] = np.where(tot < 0, np.where(eth_weaker, np.maximum(W[:, x.ie], 0) + tot, np.maximum(W[:, x.ie], 0)), W[:, x.ie])
    return W


PIECES += [
    ("atr_trail_long", "exit", "volatility trailing stop on longs: out when BTC is p x its daily range below the high since entry", (3, 5, 8), atr_trail_long),
    ("ma_cross_exit", "exit", "longs only while BTC's fast average is above its slow one (p = days)", ((10, 30), (20, 50), (50, 100)), ma_cross_exit),
    ("rsi_trim", "take-profit", "halve longs while BTC's 14-day RSI is above p (overbought)", (70, 75, 80), rsi_trim),
    ("rsi_cover", "take-profit", "cover shorts while BTC's 14-day RSI is below p (oversold)", (25, 30, 35), rsi_cover),
    ("neg_funding_boost", "entry", "longs x p while BTC funding (7d) is negative: shorts crowded, squeeze fuel", (1.25, 1.5), neg_funding_boost),
    ("calm_leverage", "size", "longs x p while BTC's 30d volatility is below its 1-year median", (1.1, 1.25, 1.5), calm_leverage),
    ("ramp_up", "size", "size ramps from 50% to 150% over p days in a long episode", (10, 30, 60), ramp_up),
    ("dd_adaptive", "stop-loss", "book size x (1 - its drawdown / p), at least 25%", (0.2, 0.3, 0.4), dd_adaptive),
    ("eth_trend_confirm", "entry", "longs at half size unless ETH is above its p-day average too", (20, 50, 100), eth_trend_confirm),
    ("september_light", "crazy", "September (historically weakest month) at p of size", (0.0, 0.5), september_light),
    ("short_weaker", "basket", "put the whole short on whichever of BTC/ETH was weaker over p days", (14, 30, 60), short_weaker),
    ("long_size_mod", "size", "long leg x p, moderate steps", (1.1, 1.2, 1.3), HY.long_size),
    ("vt_mult_mod", "size", "every position x p, moderate steps, gross <= 100%", (1.1, 1.2, 1.3), HY.vt_multiplier),
]
BY = {p[0]: p for p in PIECES}
