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
            pen = max(0.0, (e.get("dd", 0) or 0) - (e.get("dd_champion", 0) or 0) - 0.02)
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
