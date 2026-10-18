"""Rocket - an endless search for a trade VALIDATOR on top of System 10's winning model.

The operator, 2026-10-15: "in parallel, take the winning model as it is and see whether an
external process that validates or denies its operations can raise the share it gets right ...
MAs from 1 to 300, every RSI, MACD, combinations of two and three, other markets ... 100 ideas or
10,000, one by one, and leave a record of everything." And one rule: what already works is not
touched. So Rocket only READS System 10 (its code and its frozen signal cache) and writes only
inside research/rocket/.

What one test is
    idea      a feature (an indicator on a coin / BTC / the whole market / another market / the
              calendar / the model's own forecast) and a rule type (veto above or below a
              threshold, veto some categories, a learned veto, or an OR of several ideas)
    nested    for each test year N in 2022..2025 the rule is CHOSEN on the champion's own trades
              of years 2020..N-1 only (threshold, side, categories, model), then applied to N: the
              entries it denies are removed and year N is booked again with the champion's book
    verdict   against the champion without a validator, same years, same book: per-year paired
              21-day block bootstrap (book_lab.paired) and the selection law over 2022-25
    placebo   every PLACEBO_EVERY-th test re-runs an earlier idea on its feature shifted in time by
              6-18 months, which keeps the feature's distribution and destroys its timing. The
              share of placebo ideas that "win" is the chance rate; a family is only worth
              anything if it beats it.

Two universes: "today" (System 10's 14 coins, the frozen cache book_lab uses) and "pit" (each
year's point-in-time top 14, built once by `pit-dump` into research/rocket/cache/). 2026 is never
read: test years stop at 2025.

    R=$(pwd -W); export PYTHONPATH="$R/trading-system;$R/trading-system/systems;$R/research/system10/tools;$R/backtester;$R/live-trading"
    python research/rocket/rocket.py run --hours 24      # the endless loop (watchdog relaunches it)
    python research/rocket/rocket.py pit-dump            # one-off: point-in-time signal cache
    python research/rocket/rocket.py report              # REPORT.md from the ledger
Brake: research/rocket/STOP.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import itertools
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
for sub in ("trading-system", "trading-system/systems", "research/system10/tools", "backtester", "live-trading"):
    if str(REPO / sub) not in sys.path:
        sys.path.insert(0, str(REPO / sub))

LEDGER = ROOT / "ledger.jsonl"
REPORT = ROOT / "REPORT.md"
CACHE = ROOT / "cache"
PIT_CACHE = CACHE / "pit_34.npz"
PID = CACHE / "run.pid"
STOP = ROOT / "STOP"
EXT = REPO / "trading-system/backtester/data/external"

RELEASE = 34                      # the champion the paper book follows (2026-10-15)
RULE_VERSION = 2                  # stable_gain v2: demeaned (2026-10-16); ledger_v1.jsonl holds v1
TRAIN_FROM = 2020
TEST_YEARS = (2022, 2023, 2024, 2025)
ALL_YEARS = tuple(range(TRAIN_FROM, 2026))
BAR_NS = 900 * 10**9
DAY_NS = 86_400 * 10**9
MAX_VETO_SHARE = 0.5              # a validator may deny at most half of the trades it is trained on
MIN_VETOED = 20
WIN_P = 0.90                      # book_lab's bar for "B better than A in a year"
PLACEBO_EVERY = 10
MIN_FREE_GB = 3.0
REPORT_EVERY_S = 1800


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def idea_id(idea: dict) -> str:
    return hashlib.sha1(json.dumps(idea, sort_keys=True).encode()).hexdigest()[:12]


def free_gb() -> float:
    import psutil
    return psutil.virtual_memory().available / 1e9


def wait_for_ram(gb: float = MIN_FREE_GB) -> None:
    while free_gb() < gb and not STOP.exists():
        time.sleep(60)


def law1(r, dd):
    """search.law for a single year (book_lab.paired uses the same)."""
    return 0.5 * r + 0.5 * min(r, 0.5) - 0.25 * dd


# ============================================================================ universes

class Universe:
    """Per test year: the coins' arrays, the champion's signals for that year, its book."""

    def __init__(self, name: str):
        import book_lab as BL
        self.name = name
        self.rel = BL.BI.release(RELEASE)
        self.cfg = self.rel["cfg"]
        if name == "today":
            per, meta, _ = BL.BI.load(RELEASE)
            self.meta = meta
            for d in per.values():
                d.setdefault("prob", np.full(len(d["ns"]), np.nan))
            self.worlds = {N: per for N in ALL_YEARS}
            self.sig = {N: {s: {"enter": d[f"enter{N}"], "keep": d[f"keep{N}"], "strength": d[f"strength{N}"]}
                            for s, d in per.items()} for N in ALL_YEARS}
            try:
                F = BL.BI.load_feats()
                for s, d in per.items():
                    if s in F:
                        pos = np.searchsorted(F[s]["ns"], d["ns"])
                        d["X"] = F[s]["X"][pos]
                        d["breadth"] = F[s]["breadth"][pos]
            except Exception as e:  # noqa: BLE001
                print(f"  no book_feats ({e}); x: and breadth ideas unavailable", flush=True)
        else:
            z = np.load(PIT_CACHE)
            self.meta = json.loads(str(z["meta"]))
            self.worlds, self.sig = {}, {}
            for k in z.files:
                if k == "meta":
                    continue
                N, s, f = k.split("|")
                N = int(N)
                if f in ("enter", "keep", "strength"):
                    self.sig.setdefault(N, {}).setdefault(s, {})[f] = z[k]
                else:
                    self.worlds.setdefault(N, {}).setdefault(s, {})[f] = z[k]
            for per in self.worlds.values():
                for d in per.values():
                    d.setdefault("prob", np.full(len(d["ns"]), np.nan))
        self._base: dict = {}
        self._feat: dict = {}
        self._grid: dict = {}

    def years(self):
        return [N for N in ALL_YEARS if N in self.worlds]

    def book(self, N: int, veto: dict | None = None, half: bool = False, mult: dict | None = None,
             detail: bool = False) -> dict:
        """The champion's year N; `veto` denies those entries, or with `half` enters them at
        half stake instead (a soft validator)."""
        import conditions as C
        from system010_conditioned_rl import search as S
        per, sig, cfg = self.worlds[N], self.sig[N], self.cfg
        deny = veto is not None and not half
        enter = {s: (sig[s]["enter"] & ~veto[s]) if deny else sig[s]["enter"] for s in per}
        pN = {s: {k: d[k] for k in ("ns", "close", "prob", "year")} for s, d in per.items()}
        size = ({s: d["size"] for s, d in per.items()}
                if (cfg.get("size_down", 1.0) < 1.0 or cfg.get("vol_target")) else None)
        if veto is not None and half:
            size = {s: (size[s] if size is not None else np.ones(len(d["ns"]))) * np.where(veto[s], 0.5, 1.0)
                    for s, d in per.items()}
        if mult is not None:          # sizing ideas (martingale, conviction): stake x mult at the entry bar
            size = {s: (size[s] if size is not None else np.ones(len(d["ns"]))) * mult[s] for s, d in per.items()}
        keep = {s: sig[s]["keep"] for s in per} if cfg.get("exit") == "learned" else None
        strength = {s: sig[s]["strength"] for s in per}
        old = C.HORIZON
        C.HORIZON = cfg["horizon"]
        try:
            return C.book_year(pN, enter, N, self.meta["band"], self.meta["risk"], keep=keep, size=size,
                               keep_min_hold=self.meta["exit_min_hold"], strength=strength, detail=detail,
                               **S.mm_kwargs(cfg))
        finally:
            C.HORIZON = old

    def base(self, N: int) -> dict:
        if N not in self._base:
            self._base[N] = self.book(N)
        return self._base[N]

    def grid(self, N: int) -> np.ndarray:
        if N not in self._grid:
            self._grid[N] = np.unique(np.concatenate([d["ns"] for d in self.worlds[N].values()]))
        return self._grid[N]

    def feature(self, N: int, spec: dict) -> dict | None:
        key = (id(self.worlds[N]), json.dumps(spec, sort_keys=True))
        if key not in self._feat:
            if len(self._feat) > 40:
                self._feat.pop(next(iter(self._feat)))
            try:
                self._feat[key] = compute(self, N, spec)
            except Unavailable:
                self._feat[key] = None
        return self._feat[key]


# ============================================================================ features

class Unavailable(Exception):
    pass


TF = {"15m": 1, "30m": 2, "1h": 4, "2h": 8, "4h": 16, "8h": 32, "12h": 48, "1d": 96, "3d": 288, "1w": 672}


def tf_series(ns: np.ndarray, close: np.ndarray, tf: str):
    """The closes of COMPLETED tf periods and, per bar, the index of the last period completed
    strictly before the bar's own (15m: the bar itself, it is complete at decision time)."""
    k = TF[tf]
    if k == 1:
        return close.astype(float), np.arange(len(close))
    b = ns // (BAR_NS * k)
    last = np.r_[b[1:] != b[:-1], True]
    il = np.flatnonzero(last)
    return close[il].astype(float), np.searchsorted(b[il], b, side="left") - 1


def expand(v: np.ndarray, pos: np.ndarray) -> np.ndarray:
    out = np.full(len(pos), np.nan, dtype=np.float32)
    ok = pos >= 0
    out[ok] = v[pos[ok]]
    return out


def ind(c: np.ndarray, name: str, p: dict) -> np.ndarray:
    """One indicator on a series of closes; NaN until it has its window."""
    s = pd.Series(c)
    n = int(p.get("n", 14))
    lr = np.log(s).diff()
    if name == "sma_dist":
        return (s / s.rolling(n).mean() - 1).values
    if name == "ema_dist":
        return (s / s.ewm(span=n, adjust=False, min_periods=n).mean() - 1).values
    if name == "sma_slope":
        m = s.rolling(n).mean()
        return (m / m.shift(max(1, n // 4)) - 1).values
    if name == "ma_cross":
        return (s.rolling(int(p["a"])).mean() / s.rolling(int(p["b"])).mean() - 1).values
    if name == "roc":
        return (s / s.shift(n) - 1).values
    if name == "rsi":
        d = s.diff()
        up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
        dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
        return (100 - 100 / (1 + up / dn.replace(0, np.nan))).values
    if name == "macd":
        a, b, g = int(p["a"]), int(p["b"]), int(p["sig"])
        m = s.ewm(span=a, adjust=False).mean() - s.ewm(span=b, adjust=False).mean()
        h = (m - m.ewm(span=g, adjust=False).mean()) / s
        h.iloc[:b] = np.nan
        return h.values
    if name == "vol":
        return lr.rolling(n).std().values
    if name == "vol_ratio":
        return (lr.rolling(n).std() / lr.rolling(4 * n).std()).values
    if name == "zscore":
        return ((s - s.rolling(n).mean()) / s.rolling(n).std()).values
    if name == "dd":
        return (s / s.rolling(n).max() - 1).values
    if name == "pos":
        lo, hi = s.rolling(n).min(), s.rolling(n).max()
        return ((s - lo) / (hi - lo).replace(0, np.nan)).values
    if name == "vr":          # variance ratio: > 1 trending, < 1 mean-reverting (Lo-MacKinlay)
        w = max(5 * n, 50)
        rn = np.log(s).diff(n)
        return (rn.rolling(w).var() / (n * lr.rolling(w).var())).values
    if name == "skew":
        return lr.rolling(max(n, 5)).skew().values
    if name == "kurt":
        return lr.rolling(max(n, 5)).kurt().values
    if name == "autocorr":
        return lr.rolling(max(n, 5)).corr(lr.shift(1)).values
    if name == "efficiency":  # Kaufman: net move / path length
        return ((s - s.shift(n)).abs() / s.diff().abs().rolling(n).sum()).values
    raise ValueError(name)


def _daily_series(fname: str, lag_days: float = 2.0):
    """A daily external series as (visible-from ns, value); a value stamped day D is read from
    D + lag_days (default 2: the day must be over and published)."""
    path = EXT / f"{fname}.json"
    if not path.is_file():
        raise Unavailable(fname)
    rows = json.loads(path.read_text(encoding="utf-8"))
    t = np.array([int(r.get("t_s", r.get("t_ms", 0) / 1000)) for r in rows], dtype=np.int64) * 10**9
    v = np.array([float(r["value"]) for r in rows], dtype=float)
    o = np.argsort(t)
    return t[o] + int(lag_days * DAY_NS), v[o]


def _map_times(t_vis: np.ndarray, v: np.ndarray, ns: np.ndarray) -> np.ndarray:
    i = np.searchsorted(t_vis, ns, side="right") - 1
    out = np.full(len(ns), np.nan, dtype=np.float32)
    ok = i >= 0
    out[ok] = v[i[ok]]
    return out


def compute(u: Universe, N: int, spec: dict) -> dict:
    """{symbol: float32 per bar} for one feature spec in year N's world. Causal throughout."""
    per = u.worlds[N]
    src, name = spec["src"], spec.get("ind")
    tf = spec.get("tf", "1d")
    p = {k: v for k, v in spec.items() if k in ("n", "a", "b", "sig")}

    def own(s):
        d = per[s]
        c, pos = tf_series(d["ns"], d["close"], tf)
        return expand(ind(c, name, p), pos)

    if src == "self":
        return {s: own(s) for s in per}
    if src in ("btc", "rel"):
        if "BTCUSDT" not in per:
            raise Unavailable("btc")
        b = per["BTCUSDT"]
        bv = own("BTCUSDT")
        out = {}
        for s, d in per.items():
            i = np.clip(np.searchsorted(b["ns"], d["ns"], side="right") - 1, 0, None)
            out[s] = bv[i] if src == "btc" else own(s) - bv[i]
        return out
    if src in ("mkt_below", "mkt_mean", "mkt_disp", "rank"):
        g = u.grid(N)
        syms = list(per)
        M = np.full((len(g), len(syms)), np.nan, dtype=np.float32)
        pos = {}
        for j, s in enumerate(syms):
            pos[s] = np.searchsorted(g, per[s]["ns"])
            M[pos[s], j] = own(s)
        fin = np.isfinite(M)
        cnt = fin.sum(axis=1)
        with np.errstate(all="ignore"):
            if src == "mkt_below":
                agg = np.where(cnt >= 3, (np.nan_to_num(M, nan=1.0) < 0).sum(axis=1) / np.maximum(cnt, 1), np.nan)
            elif src == "mkt_mean":
                agg = np.where(cnt >= 3, np.nanmean(np.where(fin, M, np.nan), axis=1), np.nan)
            elif src == "mkt_disp":
                agg = np.where(cnt >= 3, np.nanstd(np.where(fin, M, np.nan), axis=1), np.nan)
            else:
                r = pd.DataFrame(M).rank(axis=1, pct=True).values
                return {s: r[pos[s], j].astype(np.float32) for j, s in enumerate(syms)}
        return {s: agg[pos[s]].astype(np.float32) for s in syms}
    if src == "x":
        from system010_conditioned_rl import features as FR
        j = FR.MARKET.index(name)
        if not all("X" in d for d in per.values()):
            raise Unavailable("x")
        return {s: d["X"][:, j].astype(np.float32) for s, d in per.items()}
    if src == "breadth":
        if not all("breadth" in d for d in per.values()):
            raise Unavailable("breadth")
        return {s: d["breadth"].astype(np.float32) for s, d in per.items()}
    if src == "macro":
        from system006_oracle_net_15m.reference import ReferenceTable
        ref = ReferenceTable()
        j = list(ref.cols).index(name)
        return {s: ref.matrix_for(d["ns"].astype("datetime64[ns]"))[:, j].astype(np.float32) for s, d in per.items()}
    if src == "funding":
        k = int(spec.get("n", 1))
        out = {}
        for s, d in per.items():
            f = EXT / f"funding_{s}.json"
            if not f.is_file():
                out[s] = np.full(len(d["ns"]), np.nan, dtype=np.float32)
                continue
            rows = json.loads(f.read_text(encoding="utf-8"))
            t = np.array([r["t_ms"] for r in rows], dtype=np.int64) * 10**6
            v = pd.Series([float(r["rate"]) for r in rows]).rolling(k).mean().values
            i = np.searchsorted(t, d["ns"], side="left") - 1          # settled strictly before the bar
            o = np.full(len(d["ns"]), np.nan, dtype=np.float32)
            ok = i >= 0
            o[ok] = v[i[ok]]
            out[s] = o
        if all(np.isnan(o).all() for o in out.values()):
            raise Unavailable("funding")
        return out
    if src == "daily":            # feargreed, oi_BTCUSDT, stablecoin_supply, etf_flow_btc
        t, v = _daily_series(name)
        k = int(spec.get("n", 1))
        if spec.get("chg"):
            v = pd.Series(v).pct_change(k).values
        elif k > 1:
            v = pd.Series(v).rolling(k).mean().values
        return {s: _map_times(t, v, d["ns"]) for s, d in per.items()}
    if src == "cal":
        out = {}
        for s, d in per.items():
            t = d["ns"]
            if name == "hour4":
                out[s] = ((t // (3600 * 10**9)) % 24 // 4).astype(np.float32)
            elif name == "hour":
                out[s] = ((t // (3600 * 10**9)) % 24).astype(np.float32)
            elif name == "dow":
                out[s] = ((t // DAY_NS + 3) % 7).astype(np.float32)      # 0 = Monday
            else:
                raise ValueError(name)
        return out
    if src == "model":            # the champion's own forecast for year N (walk-forward per year)
        return {s: u.sig[N][s]["strength"].astype(np.float32) for s in per}
    if src == "coin":             # per-coin identity: a validator that learns which coins fail
        return {s: np.full(len(d["ns"]), float(sorted(per).index(s)), dtype=np.float32) for s, d in per.items()}
    raise ValueError(src)


def shifted(u: Universe, N: int, spec: dict, days: int) -> dict | None:
    """The placebo: the same feature shifted later in time by `days` within each coin's research
    bars (the values of an earlier period stand at each bar) - distribution kept, timing gone."""
    f = u.feature(N, spec)
    if f is None:
        return None
    out = {}
    for s, v in f.items():
        d = u.worlds[N][s]
        res = np.flatnonzero(d["year"] <= 2025)
        w = v.copy()
        k = days * 96
        if len(res) > k:
            seg = v[res]
            w[res] = np.r_[seg[-k:], seg[:-k]]
        out[s] = w
    return out


# ============================================================================ rules (nested)

def entry_rows(u: Universe, years, f_of) -> tuple:
    """The champion's trades of `years` with the feature at entry: (values, returns, years)."""
    vals, rets, yrs = [], [], []
    for M in years:
        f = f_of(M)
        if f is None:
            continue
        for s, bar, ret in u.base(M)["trade_log"]:
            vals.append(f[s][bar])
            rets.append(ret)
            yrs.append(M)
    return np.asarray(vals, float), np.asarray(rets, float), np.asarray(yrs, int)


def stable_gain(veto: np.ndarray, rets: np.ndarray, yrs: np.ndarray) -> tuple[float, bool]:
    """Gain of denying `veto` trades RELATIVE TO THAT YEAR'S AVERAGE TRADE, and whether it is
    positive in at least two thirds of the training years that have trades.

    v2 (2026-10-16): v1 scored minus the denied trades' summed return. Where the champion lost
    money in the training years (point-in-time 2020-23) that made denying ANY half look good -
    RSI 4h 80 was learned with opposite sides in two runs and both 'helped' - so the rules were
    really "trade less". Demeaned, denying a random subset scores ~0: only denying trades worse
    than the ones kept counts (a denied entry frees a slot for another, average one)."""
    ys = np.unique(yrs)
    g = np.array([-(rets[veto & (yrs == y)] - rets[yrs == y].mean()).sum() for y in ys])
    need = int(np.ceil(2 * len(ys) / 3))
    return float(g.sum()), bool((g > 0).sum() >= need)


QS_HI = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
QS_LO = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5)


def choose_thr(vals, rets, yrs) -> dict | None:
    ok = np.isfinite(vals)
    if ok.sum() < 3 * MIN_VETOED:
        return None
    v, r, y = vals[ok], rets[ok], yrs[ok]
    best = None
    for side, qs in ((">", QS_HI), ("<", QS_LO)):
        for q in qs:
            thr = float(np.quantile(v, q))
            veto = v > thr if side == ">" else v < thr
            if veto.sum() < MIN_VETOED or veto.mean() > MAX_VETO_SHARE:
                continue
            gain, stable = stable_gain(veto, r, y)
            if stable and gain > 0 and (best is None or gain > best["gain"]):
                best = {"side": side, "thr": thr, "q": q, "gain": round(gain, 4), "share": round(float(veto.mean()), 3)}
    return best


BANDS = ((0.05, 0.95), (0.1, 0.9), (0.15, 0.85), (0.2, 0.8), (0.25, 0.75), (0.05, 0.8), (0.2, 0.95), (0.1, 0.75), (0.25, 0.9))


def choose_band(vals, rets, yrs) -> dict | None:
    """Deny the EXTREMES (both tails at once) when the past says extremes lose."""
    ok = np.isfinite(vals)
    if ok.sum() < 3 * MIN_VETOED:
        return None
    v, r, y = vals[ok], rets[ok], yrs[ok]
    best = None
    for lo, hi in BANDS:
        a, b = float(np.quantile(v, lo)), float(np.quantile(v, hi))
        veto = (v < a) | (v > b)
        if veto.sum() < MIN_VETOED or veto.mean() > MAX_VETO_SHARE:
            continue
        gain, stable = stable_gain(veto, r, y)
        if stable and gain > 0 and (best is None or gain > best["gain"]):
            best = {"band": [a, b], "q": [lo, hi], "gain": round(gain, 4), "share": round(float(veto.mean()), 3)}
    return best


def choose_cat(vals, rets, yrs) -> dict | None:
    ok = np.isfinite(vals)
    v, r, y = vals[ok], rets[ok], yrs[ok]
    bad = []
    for c in np.unique(v):
        m = v == c
        if m.sum() >= MIN_VETOED:
            gain, stable = stable_gain(m, r, y)
            if stable and gain > 0:
                bad.append((gain, float(c), m.mean()))
    bad.sort(reverse=True)
    cats, share = [], 0.0
    for gain, c, sh in bad:
        if share + sh > MAX_VETO_SHARE:
            break
        cats.append(c)
        share += sh
    return {"cats": cats, "share": round(share, 3)} if cats else None


def apply_rule(rule: dict | None, f: dict) -> dict:
    out = {}
    for s, v in f.items():
        if rule is None:
            out[s] = np.zeros(len(v), dtype=bool)
        elif "cats" in rule:
            out[s] = np.isin(v, rule["cats"])
        elif "band" in rule:
            with np.errstate(invalid="ignore"):
                out[s] = ((v < rule["band"][0]) | (v > rule["band"][1])) & np.isfinite(v)
        else:
            with np.errstate(invalid="ignore"):
                out[s] = (v > rule["thr"]) if rule["side"] == ">" else (v < rule["thr"])
            out[s] &= np.isfinite(v)
    return out


def single_veto(u: Universe, idea: dict, N: int, f_of) -> tuple[dict | None, dict | None]:
    vals, rets, yrs = entry_rows(u, range(TRAIN_FROM, N), f_of)
    kind = idea.get("rule")
    rule = (choose_cat(vals, rets, yrs) if kind == "cat" else choose_band(vals, rets, yrs) if kind == "band"
            else choose_thr(vals, rets, yrs))
    fN = f_of(N)
    if fN is None:
        return None, None
    return apply_rule(rule, fN), rule


ML_BANKS = {
    "core": [{"src": "self", "ind": i, "tf": t, "n": n} for i in ("sma_dist", "rsi", "vol", "dd", "roc")
             for t in ("1d", "4h") for n in (5, 20, 50)]
            + [{"src": "btc", "ind": i, "tf": "1d", "n": n} for i in ("sma_dist", "roc", "vol") for n in (10, 50, 200)]
            + [{"src": "mkt_below", "ind": "sma_dist", "tf": "1d", "n": n} for n in (20, 50, 200)]
            + [{"src": "model"}, {"src": "breadth"}, {"src": "cal", "ind": "hour4"}],
    "x44": "x44",
    "macro": [{"src": "macro", "ind": c} for c in ("ref_vix_pct", "ref_vix_chg20", "ref_ndx_ret20", "ref_ndx_ret60",
                                                    "ref_dxy_chg20", "ref_oil_ret20", "ref_y10_chg20", "ref_curve")]
             + [{"src": "funding", "n": k} for k in (1, 9)] + [{"src": "daily", "ind": "feargreed"}],
}


def bank(name: str) -> list[dict]:
    if name == "x44":
        from system010_conditioned_rl import features as FR
        return [{"src": "x", "ind": c} for c in FR.MARKET] + [{"src": "breadth"}]
    if name == "all":
        return ML_BANKS["core"] + bank("x44") + ML_BANKS["macro"]
    return ML_BANKS[name]


def ml_veto(u: Universe, idea: dict, N: int) -> tuple[dict | None, dict | None]:
    """A learned validator: gradient-boosted trees on the bank at entry, label = the trade made
    money. Threshold chosen on leave-one-year-out predictions of the training years, then the
    model is refitted on all of them and applied to N."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    specs = bank(idea["ml"])
    fs = {M: [u.feature(M, sp) for sp in specs] for M in range(TRAIN_FROM, N + 1)}
    keep_cols = [j for j in range(len(specs)) if all(fs[M][j] is not None for M in fs)]
    if len(keep_cols) < 3:
        return None, None
    rows, rets, yrs = [], [], []
    for M in range(TRAIN_FROM, N):
        for s, bar, ret in u.base(M)["trade_log"]:
            rows.append([fs[M][j][s][bar] for j in keep_cols])
            rets.append(ret)
            yrs.append(M)
    X, r, y = np.asarray(rows, float), np.asarray(rets, float), np.asarray(yrs, int)
    if len(X) < 300 or len(np.unique(y)) < 2:
        return None, None

    def model():
        return HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05,
                                              l2_regularization=1.0, min_samples_leaf=40, random_state=7)
    oof = np.full(len(X), np.nan)
    for M in np.unique(y):
        tr = y != M
        if len(np.unique(r[tr] > 0)) < 2:
            continue
        oof[y == M] = model().fit(X[tr], r[tr] > 0).predict_proba(X[y == M])[:, 1]
    rule = choose_thr(oof, r, y)
    if rule is None or rule["side"] != "<":
        return {s: np.zeros(len(d["ns"]), bool) for s, d in u.worlds[N].items()}, None
    m = model().fit(X, r > 0)
    out = {}
    for s, d in u.worlds[N].items():
        cand = np.flatnonzero(u.sig[N][s]["enter"] & (d["year"] == N))
        v = np.zeros(len(d["ns"]), bool)
        if len(cand):
            Z = np.column_stack([fs[N][j][s][cand] for j in keep_cols])
            v[cand] = m.predict_proba(Z)[:, 1] < rule["thr"]
        out[s] = v
    return out, {**rule, "cols": len(keep_cols)}


def veto_for(u: Universe, idea: dict, N: int, placebo_days: int | None = None):
    if "combo" in idea:
        masks, rules = None, []
        for part in idea["combo"]:
            m, rule = veto_for(u, part, N)
            rules.append(rule)
            if m is None:
                return None, rules
            masks = m if masks is None else {s: masks[s] | m[s] for s in masks}
        return masks, rules
    if "ml" in idea:
        return ml_veto(u, idea, N)
    if placebo_days:
        def f_of(M):
            return shifted(u, M, idea["f"], placebo_days)
    else:
        def f_of(M):
            return u.feature(M, idea["f"])
    return single_veto(u, idea, N, f_of)


# ============================================================================ sizing ideas (2026-10-18)

def martingale_mult(u: "Universe", N: int, mg: dict, shuffle: int | None = None) -> tuple[dict, float]:
    """Stake multipliers for year N from the book's OWN closed trades before each entry.

    mode  loss    classic martingale: x base^k after k losses in a row (k <= kmax), capped
          win     anti-martingale: the same after k wins in a row
          defend  the opposite of loss: / base^k after k losses (floor 1 / cap)
    risk  no increase while the account is more than `dd_gate` below its high (the "risk
          minimised" part); `cap` bounds the stake; `kmax` bounds the streak.
    Two passes (the trades barely change with size; the second pass reads the first's
    outcomes). `shuffle` = the placebo: the same rule on a randomly reordered outcome sequence."""
    per = u.worlds[N]
    mult = {s: np.ones(len(d["ns"])) for s, d in per.items()}
    changed = 0.0
    for _ in range(2):
        r = u.book(N, mult=mult, detail=True)
        fills = r.get("fills") or []
        closes = [(f["t"], f.get("realised", 0.0) > 0) for f in fills
                  if f["side"] == "SELL" and not str(f["reason"]).startswith("trim")]
        wins = [w for _, w in closes]
        if shuffle is not None:
            random.Random(shuffle).shuffle(wins)
        ct = np.array([t for t, _ in closes], dtype=np.int64)
        eq = r.get("equity_curve") or []
        et = np.array([x[0] for x in eq], dtype=np.int64)
        edd = np.array([1 - x[1] / x[2] if x[2] else 0.0 for x in eq])
        new = {s: np.ones(len(d["ns"])) for s, d in per.items()}
        entries = [f for f in fills if f["side"] == "BUY" and f["reason"] == "entry"]
        n_mod = 0
        for f in entries:
            k = int(np.searchsorted(ct, f["t"], side="left"))
            want = mg["mode"] != "win"           # loss / defend count losses; win counts wins
            streak = 0
            for w in reversed(wins[:k]):
                if (not w) == want:
                    streak += 1
                else:
                    break
            streak = min(streak, int(mg["kmax"]))
            m = float(mg["base"]) ** streak
            m = 1.0 / m if mg["mode"] == "defend" else m
            m = float(np.clip(m, 1.0 / float(mg["cap"]), float(mg["cap"])))
            if mg.get("dd_gate") is not None and m > 1 and len(et):
                i = max(0, int(np.searchsorted(et, f["t"], side="right")) - 1)
                if edd[i] > float(mg["dd_gate"]):
                    m = 1.0
            j = int(np.searchsorted(per[f["symbol"]]["ns"], f["t"]))
            if j < len(new[f["symbol"]]):
                new[f["symbol"]][j] = m
                n_mod += m != 1.0
        mult = new
        changed = n_mod / max(1, len(entries))
    return mult, changed


CONDITIONS = {
    "above50": {"src": "self", "ind": "sma_dist", "tf": "1d", "n": 50},
    "above100": {"src": "self", "ind": "sma_dist", "tf": "1d", "n": 100},
    "above200": {"src": "self", "ind": "sma_dist", "tf": "1d", "n": 200},
    "slope50": {"src": "self", "ind": "sma_slope", "tf": "1d", "n": 50},
    "rsi_good": {"src": "self", "ind": "rsi", "tf": "1d", "n": 14},
    "btc200": {"src": "btc", "ind": "sma_dist", "tf": "1d", "n": 200},
    "trend4h": {"src": "self", "ind": "sma_dist", "tf": "4h", "n": 50},
    "market_up": {"src": "mkt_below", "ind": "sma_dist", "tf": "1d", "n": 50},
    "breadth": {"src": "breadth"},
    "forecast": {"src": "model"},
}


def _cond_true(name: str, v: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        if name == "rsi_good":
            return (v >= 50) & (v <= 70)
        if name == "market_up":
            return v < 0.5                      # fewer than half the coins below their 50-day MA
        if name == "breadth":
            return v >= 0.5
        if name == "forecast":
            return v >= 0.006                   # twice the entry threshold
        return v > 0


def conviction_mult(u: "Universe", N: int, cv: dict, placebo_days: int | None = None) -> tuple[dict, float]:
    """Stake multipliers from a conviction score = share of the chosen bullish conditions that
    hold at the bar (no fitting: the conditions and the mapping are fixed in the idea).

    map  top     x boost when EVERY condition holds, else 1
         linear  lo + (hi - lo) x score
         split   x boost when score >= q, x cut when score <= 1 - q, else 1"""
    per = u.worlds[N]
    flags = []
    for name in cv["conds"]:
        f = shifted(u, N, CONDITIONS[name], placebo_days) if placebo_days else u.feature(N, CONDITIONS[name])
        if f is None:
            raise Unavailable(name)
        flags.append({s: _cond_true(name, f[s]) for s in per})
    score = {s: np.mean([fl[s] for fl in flags], axis=0) for s in per}
    out, mod, cnt = {}, 0, 0
    for s, d in per.items():
        sc = score[s]
        if cv["map"] == "top":
            m = np.where(sc >= 1.0, float(cv["boost"]), 1.0)
        elif cv["map"] == "linear":
            m = float(cv["lo"]) + (float(cv["hi"]) - float(cv["lo"])) * sc
        else:
            q = float(cv["q"])
            m = np.where(sc >= q, float(cv["boost"]), np.where(sc <= 1 - q, float(cv["cut"]), 1.0))
        out[s] = m
        e = u.sig[N][s]["enter"] & (d["year"] == N)
        mod += int((m[e] != 1.0).sum())
        cnt += int(e.sum())
    return out, mod / max(1, cnt)


def evaluate_sizing(u: "Universe", idea: dict, placebo_days: int | None = None) -> dict | None:
    t0 = time.time()
    years, base_years = {}, {}
    import book_lab as BL
    for N in TEST_YEARS:
        if N not in u.worlds:
            continue
        try:
            info = None
            if "mg" in idea:
                mult, share = martingale_mult(u, N, idea["mg"], shuffle=placebo_days)
            elif "mine" in idea:
                mult, share, info = miner_mult(u, N, idea["mine"], shuffle=placebo_days)
            else:
                mult, share = conviction_mult(u, N, idea["cv"], placebo_days)
        except Unavailable:
            return None
        b = u.base(N)
        r = u.book(N, mult=mult) if share > 0 else b
        pb = BL.paired(b["daily"], r["daily"]) if share > 0 and len(b["daily"]) == len(r["daily"]) > 30 else None
        years[str(N)] = {"return": r["return"], "max_dd": r["max_dd"], "trades": r["trades"],
                         "win_rate": r["win_rate"], "denied_share": round(share, 4),
                         "p_better": pb["p_better"] if pb else None, "rule": info}
        base_years[str(N)] = {"return": b["return"], "max_dd": b["max_dd"], "trades": b["trades"],
                              "win_rate": b["win_rate"]}
    if not years:
        return None
    row = {"at": now(), "universe": u.name, "release": RELEASE, "rule_v": RULE_VERSION, "id": idea_id(idea),
           "idea": idea, "family": idea.get("family", "?"), "placebo_days": placebo_days, "years": years,
           "base_years": base_years, "sec": round(time.time() - t0, 1)}
    return grade(row)


def fam_martingale():
    for mode in ("loss", "win", "defend"):
        for base in (1.25, 1.5, 2.0):
            for kmax in (1, 2, 3):
                for cap in (2.0, 3.0):
                    for gate in (None, 0.08, 0.15):
                        if mode == "defend" and gate is not None:
                            continue                  # a gate only bounds increases
                        yield {"family": "martingale",
                               "mg": {"mode": mode, "base": base, "kmax": kmax, "cap": cap, "dd_gate": gate}}


COND_SETS = {
    "operator": ("above50", "above100", "above200", "rsi_good"),
    "trend": ("above50", "above100", "above200", "slope50"),
    "trend_btc": ("above50", "above100", "above200", "btc200"),
    "trend_rsi_btc": ("above50", "above100", "above200", "rsi_good", "btc200"),
    "multi_tf": ("above50", "above200", "trend4h", "slope50"),
    "market": ("above200", "btc200", "market_up", "breadth"),
    "with_model": ("above50", "above200", "rsi_good", "forecast"),
    "all": tuple(CONDITIONS),
}


def fam_conviction():
    for name, conds in COND_SETS.items():
        for boost in (1.25, 1.5, 2.0):
            yield {"family": "conviction", "cv": {"set": name, "conds": list(conds), "map": "top", "boost": boost}}
        for lo, hi in ((0.5, 1.5), (0.75, 1.25), (0.5, 2.0), (0.25, 1.75)):
            yield {"family": "conviction", "cv": {"set": name, "conds": list(conds), "map": "linear", "lo": lo, "hi": hi}}
        for q in (0.75, 1.0):
            for boost, cut in ((1.5, 0.5), (2.0, 0.5), (1.5, 0.75)):
                yield {"family": "conviction", "cv": {"set": name, "conds": list(conds), "map": "split", "q": q,
                                                      "boost": boost, "cut": cut}}


# ============================================================================ the miner (2026-10-18)
# The operator: "analyse the whole past, see which trades meet which criteria when they win more,
# and when those criteria hold today, size up - an algorithm that tries everything, one after
# another, on pre-computed data." Nested like everything else: criteria learned on the
# champion's trades of years < N, applied to year N's entries as a stake multiplier.

def _mine_bank() -> list[dict]:
    b = []
    for tf, ns in (("1d", (10, 20, 50, 100, 200)), ("4h", (20, 50, 200)), ("1h", (50, 200))):
        b += [{"src": "self", "ind": "sma_dist", "tf": tf, "n": n} for n in ns]
    b += [{"src": "self", "ind": "ema_dist", "tf": "1d", "n": 21}]
    b += [{"src": "self", "ind": "sma_slope", "tf": "1d", "n": n} for n in (20, 50, 200)]
    b += [{"src": "self", "ind": "roc", "tf": "1d", "n": n} for n in (1, 3, 7, 14, 30, 90)]
    b += [{"src": "self", "ind": "roc", "tf": "4h", "n": n} for n in (6, 24)]
    b += [{"src": "self", "ind": "rsi", "tf": "1d", "n": n} for n in (7, 14, 28)]
    b += [{"src": "self", "ind": "rsi", "tf": tf, "n": 14} for tf in ("4h", "1h")]
    b += [{"src": "self", "ind": "macd", "tf": tf, "a": 12, "b": 26, "sig": 9} for tf in ("1d", "4h")]
    b += [{"src": "self", "ind": "vol", "tf": "1d", "n": n} for n in (7, 30)] + [{"src": "self", "ind": "vol", "tf": "4h", "n": 24}]
    b += [{"src": "self", "ind": "vol_ratio", "tf": "1d", "n": 7}, {"src": "self", "ind": "zscore", "tf": "1d", "n": 20}]
    b += [{"src": "self", "ind": "dd", "tf": "1d", "n": n} for n in (30, 90, 365)]
    b += [{"src": "self", "ind": "pos", "tf": "1d", "n": n} for n in (20, 100)]
    b += [{"src": "self", "ind": i, "tf": "1d", "n": n} for i, n in (("vr", 20), ("skew", 30), ("kurt", 30),
                                                                     ("autocorr", 30), ("efficiency", 20))]
    b += [{"src": "btc", "ind": "sma_dist", "tf": "1d", "n": n} for n in (50, 200)]
    b += [{"src": "btc", "ind": "roc", "tf": "1d", "n": n} for n in (7, 30)]
    b += [{"src": "btc", "ind": "vol", "tf": "1d", "n": 30}, {"src": "btc", "ind": "rsi", "tf": "1d", "n": 14}]
    b += [{"src": "rel", "ind": "roc", "tf": "1d", "n": n} for n in (7, 30)]
    b += [{"src": "rank", "ind": "roc", "tf": "1d", "n": n} for n in (7, 30, 90)]
    b += [{"src": "rank", "ind": "vol", "tf": "1d", "n": 30}, {"src": "rank", "ind": "dd", "tf": "1d", "n": 90}]
    b += [{"src": "mkt_below", "ind": "sma_dist", "tf": "1d", "n": n} for n in (50, 200)]
    b += [{"src": "mkt_mean", "ind": "roc", "tf": "1d", "n": 7}, {"src": "mkt_disp", "ind": "roc", "tf": "1d", "n": 7}]
    b += [{"src": "macro", "ind": c} for c in ("ref_vix_pct", "ref_vix_chg20", "ref_ndx_ret20", "ref_ndx_ret60",
                                               "ref_dxy_chg20", "ref_oil_ret20", "ref_y10_chg20", "ref_curve")]
    b += [{"src": "funding", "n": 3}, {"src": "daily", "ind": "feargreed", "n": 1},
          {"src": "daily", "ind": "oi_BTCUSDT", "n": 7, "chg": True}, {"src": "breadth"}, {"src": "model"},
          {"src": "cal", "ind": "hour"}, {"src": "cal", "ind": "dow"}]
    return b


MINE_BANK = _mine_bank()


def mine_table(u: "Universe") -> dict:
    """Per world N: the bank's values at the bars that matter - the champion's trade entries of
    year N and every bar where it may enter in N. Computed once per universe, cached on disk."""
    if getattr(u, "_mine", None) is not None:
        return u._mine
    path = CACHE / f"mine_{u.name}_{len(MINE_BANK)}.npz"
    out: dict = {}
    if path.is_file():
        z = np.load(path)
        for k in z.files:
            N, sym, f = k.split("|")
            out.setdefault(int(N), {}).setdefault(sym, {})[f] = z[k]
        u._mine = out
        return out
    t0 = time.time()
    for N in ([] if u.name == "today" else u.years()):
        per = u.worlds[N]
        idx = {}
        for sym, d in per.items():
            cand = np.flatnonzero(u.sig[N][sym]["enter"] & (d["year"] == N))
            ent = np.array([b for s_, b, _ in u.base(N)["trade_log"] if s_ == sym], dtype=np.int64)
            idx[sym] = np.unique(np.r_[cand, ent]).astype(np.int64)
        F = {sym: np.full((len(idx[sym]), len(MINE_BANK)), np.nan, dtype=np.float32) for sym in per}
        for j, spec in enumerate(MINE_BANK):
            try:
                f = compute(u, N, spec)
            except (Unavailable, Exception):  # noqa: BLE001 - a missing series is a NaN column
                continue
            for sym in per:
                F[sym][:, j] = f[sym][idx[sym]]
        out[N] = {sym: {"idx": idx[sym], "F": F[sym]} for sym in per}
    if u.name == "today":                # one world for every year: compute once over all years
        first = u.years()[0]
        # the today world is shared: rebuild the index over every year's entries and candidates
        per = u.worlds[first]
        idx = {}
        for sym, d in per.items():
            parts = []
            for M in u.years():
                parts.append(np.flatnonzero(u.sig[M][sym]["enter"] & (d["year"] == M)))
                parts.append(np.array([b for s_, b, _ in u.base(M)["trade_log"] if s_ == sym], dtype=np.int64))
            idx[sym] = np.unique(np.concatenate(parts)).astype(np.int64)
        F = {sym: np.full((len(idx[sym]), len(MINE_BANK)), np.nan, dtype=np.float32) for sym in per}
        for j, spec in enumerate(MINE_BANK):
            if spec["src"] == "model":       # the forecast is walk-forward PER YEAR: each bar reads its own year's
                for sym, d in per.items():
                    yr = d["year"][idx[sym]]
                    for M in u.years():
                        sel = yr == M
                        F[sym][sel, j] = u.sig[M][sym]["strength"][idx[sym][sel]]
                continue
            try:
                f = compute(u, first, spec)
            except (Unavailable, Exception):  # noqa: BLE001
                continue
            for sym in per:
                F[sym][:, j] = f[sym][idx[sym]]
        tab = {sym: {"idx": idx[sym], "F": F[sym]} for sym in per}
        out = {M: tab for M in u.years()}
    save = {f"{N}|{sym}|{k}": v for N, t in out.items() for sym, d in t.items() for k, v in d.items()}
    np.savez_compressed(path, **save)
    print(f"[{now()}] miner table for {u.name}: {len(MINE_BANK)} features in {(time.time() - t0) / 60:.1f} min", flush=True)
    u._mine = out
    return out


def _rows_at(tab: dict, sym: str, bars: np.ndarray) -> np.ndarray:
    t = tab[sym]
    pos = np.searchsorted(t["idx"], bars)
    pos = np.clip(pos, 0, len(t["idx"]) - 1)
    out = t["F"][pos].copy()
    out[t["idx"][pos] != bars] = np.nan
    return out


def _train(u: "Universe", N: int, shuffle: int | None):
    tab = mine_table(u)
    X, e, y, w = [], [], [], []
    for M in range(TRAIN_FROM, N):
        if M not in u.worlds:
            continue
        log = u.base(M)["trade_log"]
        if not log:
            continue
        r = np.array([x[2] for x in log], dtype=float)
        dm = r - r.mean()
        if shuffle is not None:                         # the placebo: returns no longer belong to their trades
            np.random.default_rng(shuffle + M).shuffle(dm)
        for (sym, bar, _), v in zip(log, dm):
            X.append(_rows_at(tab[M], sym, np.array([bar]))[0])
        e.append(dm)
        y.append(np.full(len(dm), M))
        w.append(r)
    if not e:
        return None
    return np.asarray(X, dtype=np.float32), np.concatenate(e), np.concatenate(y), np.concatenate(w)


def _bin_score(m: np.ndarray, e: np.ndarray, y: np.ndarray, min_n: int = 30):
    n = int(m.sum())
    if n < min_n or m.mean() > 0.5:
        return None
    ys = np.unique(y[m])
    g = np.array([e[m & (y == k)].sum() for k in ys])
    if (g > 0).sum() < int(np.ceil(2 * len(ys) / 3)):
        return None
    sd = e[m].std() + 1e-9
    return float(e[m].mean() / sd * np.sqrt(n))


def mine_rules(X, e, y, K: int, pairs: bool) -> list[dict]:
    """Regions (one feature in a quintile, or two features in a tercile cell) whose trades beat
    their year's average trade, stable in two thirds of the training years, ranked by t-score."""
    found = []
    best_by_feat = {}
    for j in range(X.shape[1]):
        v = X[:, j]
        ok = np.isfinite(v)
        if ok.sum() < 150:
            continue
        edges = np.unique(np.nanquantile(v[ok], [0.2, 0.4, 0.6, 0.8]))
        for b in range(len(edges) + 1):
            lo = -np.inf if b == 0 else edges[b - 1]
            hi = np.inf if b == len(edges) else edges[b]
            m = ok & (v > lo) & (v <= hi)
            sc = _bin_score(m, e, y)
            if sc is not None:
                found.append({"conds": [(j, float(lo), float(hi))], "score": sc})
                best_by_feat[j] = max(best_by_feat.get(j, -9), sc)
    if pairs:
        top = sorted(best_by_feat, key=lambda j: -best_by_feat[j])[:15]
        for a, b in itertools.combinations(top, 2):
            va, vb = X[:, a], X[:, b]
            ok = np.isfinite(va) & np.isfinite(vb)
            if ok.sum() < 150:
                continue
            ea = np.unique(np.nanquantile(va[ok], [1 / 3, 2 / 3]))
            eb = np.unique(np.nanquantile(vb[ok], [1 / 3, 2 / 3]))
            ba = [-np.inf, *ea, np.inf]
            bb = [-np.inf, *eb, np.inf]
            for i in range(len(ba) - 1):
                for k in range(len(bb) - 1):
                    m = ok & (va > ba[i]) & (va <= ba[i + 1]) & (vb > bb[k]) & (vb <= bb[k + 1])
                    sc = _bin_score(m, e, y)
                    if sc is not None:
                        found.append({"conds": [(a, float(ba[i]), float(ba[i + 1])), (b, float(bb[k]), float(bb[k + 1]))],
                                      "score": sc})
    found.sort(key=lambda r: -r["score"])
    good = [r for r in found if r["score"] > 0][:K]
    return good


def _in_regions(F: np.ndarray, regions: list[dict]) -> np.ndarray:
    hit = np.zeros(len(F), dtype=bool)
    for r in regions:
        m = np.ones(len(F), dtype=bool)
        for j, lo, hi in r["conds"]:
            v = F[:, j]
            with np.errstate(invalid="ignore"):
                m &= np.isfinite(v) & (v > lo) & (v <= hi)
        hit |= m
    return hit


def _ml_model():
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(max_depth=3, max_iter=200, learning_rate=0.05, min_samples_leaf=50,
                                         l2_regularization=1.0, random_state=7)


def miner_mult(u: "Universe", N: int, mn: dict, shuffle: int | None = None) -> tuple[dict, float, dict]:
    tr = _train(u, N, shuffle)
    per = u.worlds[N]
    ones = {sym: np.ones(len(d["ns"])) for sym, d in per.items()}
    if tr is None or len(tr[1]) < 300:
        return ones, 0.0, {"why": "too few training trades"}
    X, e, y, raw = tr
    tab = mine_table(u)[N]
    info: dict = {}
    drop = None
    if mn.get("subset") is not None:          # the endless search: a random subset of the bank
        keep = np.zeros(len(MINE_BANK), dtype=bool)
        keep[np.random.default_rng(int(mn["subset"])).choice(len(MINE_BANK), int(mn.get("k_feat", 20)), replace=False)] = True
        drop = ~keep
        X = X.copy()
        X[:, drop] = np.nan
        info["features"] = [describe({"f": MINE_BANK[j]}) for j in np.flatnonzero(keep)]
    if mn["method"] == "rules":
        regions = mine_rules(X, e, y, int(mn["K"]), bool(mn["pairs"]))
        if not regions:
            return ones, 0.0, {"why": "no stable region"}
        hit_train = _in_regions(X, regions)
        info = {"regions": [{"conds": [[describe({"f": MINE_BANK[j]}), round(lo, 4), round(hi, 4)] for j, lo, hi in r["conds"]],
                             "t": round(r["score"], 2)} for r in regions],
                "train_win_in": round(float((raw[hit_train] > 0).mean()), 4) if hit_train.any() else None,
                "train_win_out": round(float((raw[~hit_train] > 0).mean()), 4) if (~hit_train).any() else None,
                "train_share": round(float(hit_train.mean()), 4)}

        def score_fn(F):
            return _in_regions(F, regions)
    else:
        q = float(mn["q"])
        oof = np.full(len(e), np.nan)
        for M in np.unique(y):
            tr_m = y != M
            if len(np.unique(y[tr_m])) < 1 or tr_m.sum() < 200:
                continue
            oof[y == M] = _ml_model().fit(X[tr_m], e[tr_m]).predict(X[y == M])
        ok = np.isfinite(oof)
        if ok.sum() < 200:
            return ones, 0.0, {"why": "too few out-of-fold rows"}
        thr = float(np.quantile(oof[ok], 1 - q))
        top = ok & (oof >= thr)
        ys = np.unique(y[top])
        g = np.array([e[top & (y == k)].sum() for k in ys])
        if (g > 0).sum() < int(np.ceil(2 * len(ys) / 3)) or g.sum() <= 0:
            return ones, 0.0, {"why": "out-of-fold top not stable"}
        model = _ml_model().fit(X, e)
        thr_full = float(np.quantile(model.predict(X), 1 - q))
        info = {"oof_top_win": round(float((raw[top] > 0).mean()), 4), "oof_rest_win": round(float((raw[ok & ~top] > 0).mean()), 4)}

        def score_fn(F):
            return model.predict(F) >= thr_full
    boost, cut = float(mn["boost"]), float(mn.get("cut", 1.0))
    mult, mod, cnt = {}, 0, 0
    for sym, d in per.items():
        m = np.ones(len(d["ns"]))
        t = tab[sym]
        sel = t["idx"][(d["year"][t["idx"]] == N)]
        if len(sel):
            F = _rows_at(tab, sym, sel)
            if drop is not None:
                F[:, drop] = np.nan
            hit = score_fn(F)
            m[sel] = np.where(hit, boost, cut)
        mult[sym] = m
        e_ = u.sig[N][sym]["enter"] & (d["year"] == N)
        mod += int((m[e_] != 1.0).sum())
        cnt += int(e_.sum())
    # how the criteria held in year N, on the champion's own trades (same entries as the baseline)
    log = u.base(N)["trade_log"]
    if log:
        hits, wins = [], []
        for sym, bar, r in log:
            F = _rows_at(tab, sym, np.array([bar]))
            if drop is not None:
                F[:, drop] = np.nan
            hits.append(bool(score_fn(F)[0]))
            wins.append(r > 0)
        hits, wins = np.array(hits), np.array(wins)
        info.update({"fwd_win_in": round(float(wins[hits].mean()), 4) if hits.any() else None,
                     "fwd_win_out": round(float(wins[~hits].mean()), 4) if (~hits).any() else None,
                     "fwd_n_in": int(hits.sum()), "fwd_n": int(len(hits))})
    return mult, mod / max(1, cnt), info


def fam_miner():
    for K in (1, 3, 10, 30):
        for pairs in (False, True):
            for boost, cut in ((1.5, 1.0), (2.0, 1.0), (1.5, 0.5), (2.0, 0.5)):
                yield {"family": "miner", "mine": {"method": "rules", "K": K, "pairs": pairs, "boost": boost, "cut": cut}}
    for q in (0.1, 0.2, 0.3):
        for boost, cut in ((1.5, 1.0), (2.0, 1.0), (1.5, 0.5), (2.0, 0.5)):
            yield {"family": "miner", "mine": {"method": "ml", "q": q, "boost": boost, "cut": cut}}


# ============================================================================ one test

def evaluate(u: Universe, idea: dict, placebo_days: int | None = None) -> dict | None:
    if "mg" in idea or "cv" in idea or "mine" in idea:
        return evaluate_sizing(u, idea, placebo_days)
    t0 = time.time()
    years, base_years = {}, {}
    for N in TEST_YEARS:
        if N not in u.worlds:
            continue
        masks, rule = veto_for(u, idea, N, placebo_days)
        if masks is None:
            return None                                   # the feature does not exist here
        b = u.base(N)
        denied = sum(int((masks[s] & u.sig[N][s]["enter"] & (u.worlds[N][s]["year"] == N)).sum()) for s in masks)
        allowed = sum(int((u.sig[N][s]["enter"] & (u.worlds[N][s]["year"] == N)).sum()) for s in masks)
        r = u.book(N, masks, half=idea.get("act") == "half") if denied else b
        import book_lab as BL
        pb = BL.paired(b["daily"], r["daily"]) if denied and len(b["daily"]) == len(r["daily"]) > 30 else None
        years[str(N)] = {"return": r["return"], "max_dd": r["max_dd"], "trades": r["trades"],
                         "win_rate": r["win_rate"], "denied_share": round(denied / max(allowed, 1), 4),
                         "p_better": pb["p_better"] if pb else None, "rule": rule}
        base_years[str(N)] = {"return": b["return"], "max_dd": b["max_dd"], "trades": b["trades"],
                              "win_rate": b["win_rate"]}
    if not years:
        return None
    row = {"at": now(), "universe": u.name, "release": RELEASE, "rule_v": RULE_VERSION, "id": idea_id(idea), "idea": idea,
           "family": idea.get("family", "?"), "placebo_days": placebo_days, "years": years,
           "base_years": base_years, "sec": round(time.time() - t0, 1)}
    return grade(row)


def grade(row: dict) -> dict:
    """The verdict, from the row's own years and its baseline years (rescore re-runs this).

    Years where neither the champion nor the validated book traded (point-in-time 2022: the
    take-bar admits nothing) carry no information and are left out of the year counts; a year
    the champion traded must keep >= 50 trades, or the champion's own count if that is lower."""
    from system010_conditioned_rl import search as S
    years, base_years = row["years"], row["base_years"]
    law = S.law(years, max(v["max_dd"] for v in years.values()))
    base_law = S.law(base_years, max(v["max_dd"] for v in base_years.values()))
    eff = [k for k in years if years[k]["trades"] > 0 or base_years[k]["trades"] > 0]
    better = sum(law1(years[k]["return"], years[k]["max_dd"]) > law1(base_years[k]["return"], base_years[k]["max_dd"]) + 1e-9
                 for k in eff)
    sig = sum((years[k]["p_better"] or 0) >= WIN_P for k in eff)
    dd, base_dd = max(v["max_dd"] for v in years.values()), max(v["max_dd"] for v in base_years.values())
    active = sum(years[k]["denied_share"] > 0 for k in years)
    need = max(2, int(np.ceil(0.75 * len(eff))))
    trades_ok = all(years[k]["trades"] >= min(50, base_years[k]["trades"]) for k in years)
    verdict = ("win" if sig >= need and law > base_law and dd <= base_dd + 0.005 and trades_ok
               else "promising" if better >= need and law > base_law and trades_ok
               else "silent" if active == 0
               else "hurts" if law < base_law else "neutral")

    def wr(Y):
        return sum((Y[k]["win_rate"] or 0) * Y[k]["trades"] for k in Y) / max(1, sum(Y[k]["trades"] for k in Y))
    row.update({"law": round(law, 4), "base_law": round(base_law, 4), "gain": round(law - base_law, 4),
                "years_better": int(better), "years_eff": len(eff), "years_sig": int(sig), "max_dd": dd,
                "base_max_dd": base_dd, "win_rate": round(wr(years), 4), "base_win_rate": round(wr(base_years), 4),
                "verdict": verdict})
    return row


# ============================================================================ the idea cocktail

GRID_N = (2, 3, 5, 8, 10, 13, 15, 20, 21, 25, 30, 34, 37, 40, 50, 55, 60, 75, 89, 100, 120, 144, 150, 175, 200, 233, 250, 300)
RSI_N = tuple(range(2, 61)) + tuple(range(70, 301, 10))
CROSS_N = (3, 5, 8, 10, 13, 20, 21, 30, 37, 50, 55, 89, 100, 144, 150, 200, 233, 300)
INDS = ("ema_dist", "sma_slope", "roc", "vol", "vol_ratio", "zscore", "dd", "pos", "vr", "skew", "kurt", "autocorr", "efficiency")


def thr(fam, **f):
    return {"family": fam, "f": f, "rule": "thr"}


def fam_ma_scan():
    """The operator's ask: every moving average from 2 to 300 periods, on the coin, on BTC, and as
    'share of the market below its average'."""
    for tf in ("1d", "4h", "1h"):
        for n in range(2, 301):
            yield thr("ma_scan", src="self", ind="sma_dist", tf=tf, n=n)
    for src in ("btc", "mkt_below"):
        for tf in ("1d", "4h"):
            for n in range(2, 301):
                yield thr("ma_scan", src=src, ind="sma_dist", tf=tf, n=n)


def fam_rsi():
    for src in ("self", "btc"):
        for tf in ("1d", "4h", "1h"):
            for n in RSI_N:
                yield thr("rsi", src=src, ind="rsi", tf=tf, n=n)


def fam_macd():
    for src in ("self", "btc", "mkt_below"):
        for tf in ("1d", "4h", "1h"):
            for a in (3, 5, 8, 12, 19):
                for b in (13, 21, 26, 34, 55, 89):
                    if a < b:
                        for g in (5, 9, 13):
                            yield thr("macd", src=src, ind="macd", tf=tf, a=a, b=b, sig=g)


def fam_cross():
    for src in ("self", "btc"):
        for tf in ("1d", "4h"):
            for a, b in itertools.combinations(CROSS_N, 2):
                yield thr("ma_cross", src=src, ind="ma_cross", tf=tf, a=a, b=b)


def fam_indicators():
    for name in INDS:
        for tf in ("1d", "4h", "1h"):
            for n in GRID_N:
                yield thr("indicators", src="self", ind=name, tf=tf, n=n)
                yield thr("indicators", src="btc", ind=name, tf=tf, n=n)
                if name in ("roc", "ema_dist", "sma_slope", "vol"):
                    for src in ("rel", "rank", "mkt_mean", "mkt_disp"):
                        yield thr("cross_section", src=src, ind=name, tf=tf, n=n)
                if name in ("roc", "ema_dist", "sma_slope"):
                    yield thr("cross_section", src="mkt_below", ind=name, tf=tf, n=n)


def fam_data():
    """Other markets and outside data: the macro panel, funding, fear & greed, open interest,
    stablecoins, ETF flows, the 44 engine columns, breadth, the calendar, the model's forecast."""
    yield {"family": "model", "f": {"src": "model"}, "rule": "thr"}
    yield {"family": "data", "f": {"src": "breadth"}, "rule": "thr"}
    for c in ("ref_vix_pct", "ref_vix_chg20", "ref_ndx_ret20", "ref_ndx_ret60", "ref_dxy_chg20",
              "ref_oil_ret20", "ref_y10_chg20", "ref_curve"):
        yield thr("macro", src="macro", ind=c)
    for k in (1, 3, 9, 21, 63):
        yield thr("funding", src="funding", n=k)
    for name in ("feargreed", "oi_BTCUSDT", "stablecoin_supply", "etf_flow_btc"):
        for k in (1, 7, 30):
            yield thr("daily", src="daily", ind=name, n=k)
            if name != "etf_flow_btc":
                yield thr("daily", src="daily", ind=name, n=k, chg=True)
    for c in ("hour4", "hour", "dow"):
        yield {"family": "calendar", "f": {"src": "cal", "ind": c}, "rule": "cat"}
    yield {"family": "coin", "f": {"src": "coin"}, "rule": "cat"}
    from system010_conditioned_rl import features as FR
    for c in FR.MARKET:
        yield thr("engine44", src="x", ind=c)


def fam_ml():
    for b in ("core", "macro", "x44", "all"):
        yield {"family": "ml", "ml": b}


def leaders(k: int, universe: str | None = None) -> list[dict]:
    """The best single ideas by gain on either universe: win/promising first, then the best
    active neutral ones with a positive gain (so variants and combos start early)."""
    rows = [r for r in read_ledger() if (universe is None or r.get("universe") == universe)
            and not r.get("placebo_days") and "f" in r.get("idea", {}) and not r["idea"].get("act")
            and r.get("verdict") in ("win", "promising", "neutral") and r.get("gain", 0) > 0]
    rows.sort(key=lambda r: (r["verdict"] == "neutral", -r["gain"]))
    out, seen = [], set()
    for r in rows:
        key = json.dumps(r["idea"]["f"], sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append({k2: v for k2, v in r["idea"].items() if k2 != "family"})
        if len(out) >= k:
            break
    return out


TF_ORDER = ("15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w")


def neighbours_of(idea: dict) -> list[dict]:
    """The robustness test (journal 2026-10-16): the same idea at nearby periods (-2, -1, +1, +2 or
    -25%..+25% for long ones) and on the timeframes either side. A real effect survives most of
    them; a lucky period does not (rank kurt 1h n=7: n=6 and n=9 hurt)."""
    if "combo" in idea:
        out = []
        for i, part in enumerate(idea["combo"]):
            for nb in neighbours_of(part):
                parts = list(idea["combo"])
                parts[i] = nb
                out.append({"combo": parts})
        return out
    if "f" not in idea:
        return []
    f, out = idea["f"], []
    base = {k: v for k, v in idea.items() if k not in ("family",)}
    for key in ("n", "a", "b"):
        if key in f:
            v = int(f[key])
            steps = (-2, -1, 1, 2) if v < 20 else tuple(int(round(v * x)) - v for x in (0.75, 0.9, 1.1, 1.25))
            for d in steps:
                if v + d >= 2 and d != 0:
                    out.append({**base, "f": {**f, key: v + d}})
    if f.get("tf") in TF_ORDER:
        i = TF_ORDER.index(f["tf"])
        for j in (i - 1, i + 1):
            if 0 <= j < len(TF_ORDER):
                out.append({**base, "f": {**f, "tf": TF_ORDER[j]}})
    return out


def replicated(rows: list[dict] | None = None) -> list[dict]:
    """Ideas promising-or-better on BOTH coin lists (the report's replication table)."""
    by: dict = {}
    for r in (rows if rows is not None else read_ledger()):
        if r.get("years") and not r.get("placebo_days") and r.get("verdict") in ("win", "promising"):
            by.setdefault(r["id"], {})[r["universe"]] = r
    return [d["today"]["idea"] for d in by.values() if "today" in d and "pit" in d]


def fam_combos():
    """Pairs of the 25 best single validators, then triples of the best 10 - rebuilt every pass."""
    for idea in replicated():
        for nb in neighbours_of({k: v for k, v in idea.items() if k != "family"}):
            yield {"family": "robust", **nb}
    top = leaders(25)
    for t in top:
        if t.get("rule") == "thr":
            yield {"family": "half", **t, "act": "half"}
            yield {"family": "band", **t, "rule": "band"}
    for a, b in itertools.combinations(top, 2):
        yield {"family": "combo2", "combo": [a, b]}
    for a, b, c in itertools.combinations(top[:10], 3):
        yield {"family": "combo3", "combo": [a, b, c]}


def random_idea(rng: random.Random) -> dict:
    """The disruptive end: any indicator, any source, any timeframe, unusual periods; and the
    miner on a random subset of the bank (the operator: "an algorithm that tries everything")."""
    roll = rng.random()
    if roll > 0.8:
        method = rng.choice(("rules", "rules", "ml"))
        m = {"method": method, "subset": rng.randint(0, 10**6), "k_feat": rng.choice((8, 12, 20, 30)),
             "boost": rng.choice((1.5, 2.0)), "cut": rng.choice((1.0, 0.5))}
        if method == "rules":
            m.update(K=rng.choice((1, 3, 10)), pairs=rng.random() < 0.5)
        else:
            m.update(q=rng.choice((0.1, 0.2, 0.3)))
        return {"family": "miner_random", "mine": m}
    if roll < 0.15:
        top = leaders(40)
        if len(top) >= 2:
            return {"family": "random_combo", "combo": rng.sample(top, rng.choice((2, 2, 3)))}
    name = rng.choice(INDS + ("sma_dist", "rsi", "macd", "ma_cross"))
    f = {"src": rng.choice(("self", "self", "btc", "rel", "rank", "mkt_below", "mkt_mean", "mkt_disp")),
         "ind": name, "tf": rng.choice(tuple(TF))}
    if name == "macd":
        a = rng.randint(2, 30)
        f.update(a=a, b=rng.randint(a + 2, 120), sig=rng.randint(3, 20))
    elif name == "ma_cross":
        a = rng.randint(2, 150)
        f.update(a=a, b=rng.randint(a + 1, 400))
    else:
        f["n"] = rng.choice((rng.randint(2, 500), rng.choice((7, 11, 17, 19, 23, 29, 31, 37, 41, 43, 47, 61, 97))))
    if f["src"] in ("mkt_below",) and name not in ("roc", "ema_dist", "sma_slope", "sma_dist", "macd"):
        f["src"] = "mkt_mean"
    return thr("random", **f)


FAMILIES = (fam_miner, fam_martingale, fam_conviction, fam_ma_scan, fam_rsi, fam_macd, fam_cross, fam_indicators, fam_data, fam_ml)


def ideas(seed: int):
    """Round-robin over the families (so every kind of idea gets tried from the first hour), a
    combos pass whenever leaders exist, and random ideas forever."""
    rng = random.Random(seed)
    its = [f() for f in FAMILIES]
    combo_it, combo_at = None, 0
    k = 0
    while True:
        k += 1
        if its:
            it = its[k % len(its)]
            try:
                yield next(it)
            except StopIteration:
                its.remove(it)
        if k % 7 == 0:
            yield random_idea(rng)
        if k % 5 == 0:
            if combo_it is None or time.time() - combo_at > 3600:
                combo_it, combo_at = fam_combos(), time.time()
            try:
                yield next(combo_it)
            except StopIteration:
                pass
        if not its:
            yield random_idea(rng)


# ============================================================================ ledger, report

def read_ledger() -> list[dict]:
    if not LEDGER.is_file():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def append(row: dict) -> None:
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=float) + "\n")


def _fmt_years(r):
    return " ".join(f"{k[2:]}:{v['return']:+.0%}/{v['max_dd']:.0%}" for k, v in r["years"].items())


def describe(idea: dict) -> str:
    if "combo" in idea:
        return " OR ".join(describe(p) for p in idea["combo"])
    if "ml" in idea:
        return f"learned validator on bank '{idea['ml']}'"
    if "mine" in idea:
        m = idea["mine"]
        head = (f"miner rules K={m['K']}{' +pairs' if m['pairs'] else ''}" if m["method"] == "rules"
                else f"miner ML top {int(m['q'] * 100)}%")
        if m.get("subset") is not None:
            head += f" on {m.get('k_feat', 20)} random features (seed {m['subset']})"
        return f"{head} boost {m['boost']} cut {m['cut']}"
    if "mg" in idea:
        m = idea["mg"]
        return f"martingale {m['mode']} x{m['base']}^k k<={m['kmax']} cap {m['cap']} dd-gate {m['dd_gate']}"
    if "cv" in idea:
        c = idea["cv"]
        tail = (f"boost {c['boost']}" if c["map"] == "top" else f"{c['lo']}..{c['hi']}" if c["map"] == "linear"
                else f"q {c['q']} boost {c['boost']} cut {c['cut']}")
        return f"conviction {c['set']} {c['map']} {tail}"
    f = idea["f"]
    bits = [f["src"], f.get("ind", "")]
    if "tf" in f:
        bits.append(f["tf"])
    for k in ("n", "a", "b", "sig"):
        if k in f:
            bits.append(f"{k}={f[k]}")
    if f.get("chg"):
        bits.append("chg")
    return " ".join(b for b in bits if b)


DERIVED = ("combo2", "combo3", "random_combo", "robust", "half", "band", "check")


def report() -> Path:
    rows = read_ledger()
    lines = [f"# Rocket - report (auto, {now()})", "",
             "Generated from `ledger.jsonl` by `rocket.py report`. Notes by hand: `JOURNAL.md`. "
             "Gain = selection-law score over 2022-25 with the validator minus without it (same "
             "champion, same book). Return/DD per year shown as `yy:ret/dd`.", ""]
    for uni in ("today", "pit"):
        real = [r for r in rows if r.get("universe") == uni and not r.get("placebo_days") and r.get("years")]
        plac = [r for r in rows if r.get("universe") == uni and r.get("placebo_days") and r.get("years")]
        if not real:
            continue
        base = real[0]
        lines += [f"## Universe: {uni}", "",
                  f"Baseline (release {RELEASE}, no validator): law {base['base_law']:+.3f}, max DD {base['base_max_dd']:.0%}, "
                  f"win rate {base['base_win_rate']:.1%}.", ""]
        cnt = lambda rs, v: sum(r["verdict"] == v for r in rs)  # noqa: E731
        lines += ["| | tested | win | promising | neutral | hurts | silent |", "|---|---|---|---|---|---|---|",
                  f"| real ideas | {len(real)} | {cnt(real, 'win')} | {cnt(real, 'promising')} | {cnt(real, 'neutral')} | "
                  f"{cnt(real, 'hurts')} | {cnt(real, 'silent')} |",
                  f"| placebo (time-shifted) | {len(plac)} | {cnt(plac, 'win')} | {cnt(plac, 'promising')} | "
                  f"{cnt(plac, 'neutral')} | {cnt(plac, 'hurts')} | {cnt(plac, 'silent')} |", ""]
        act = lambda rs: [r for r in rs if r["verdict"] != "silent"]  # noqa: E731
        rate = lambda rs, vs: (sum(r["verdict"] in vs for r in act(rs)) / max(1, len(act(rs))))  # noqa: E731
        prim = [r for r in real if r["family"] not in DERIVED]
        der = [r for r in real if r["family"] in DERIVED]
        if plac:
            import math
            p0 = max(rate(plac, ("win", "promising")), 1e-3)
            n, k = len(act(prim)), sum(r["verdict"] in ("win", "promising") for r in act(prim))
            z = (k - n * p0) / math.sqrt(max(n * p0 * (1 - p0), 1e-9))
            lines += [f"**Evidence test (primary ideas only):** {k} / {n} = {k / max(1, n):.2%} win-or-promising vs "
                      f"placebo {p0:.2%}, z = {z:+.1f}. Derived ideas (combos, half, band, neighbours of leaders: "
                      f"{sum(r['verdict'] in ('win', 'promising') for r in act(der))} / {len(act(der))}) are built from "
                      "leaders picked on the SAME years they are graded on, so their rate is selection bias, not "
                      "evidence; they are listed for follow-up only. A z above +3 would be worth the operator's time.", ""]
            lines += [f"Chance rate: {rate(plac, ('win',)):.1%} of active placebo ideas 'win' and "
                      f"{rate(plac, ('win', 'promising')):.1%} are win-or-promising; real ideas: "
                      f"{rate(real, ('win',)):.1%} and {rate(real, ('win', 'promising')):.1%}. "
                      "A family is only interesting where it clearly beats the placebo.", ""]
        fams: dict = {}
        for r in real:
            fams.setdefault(r["family"], []).append(r)
        lines += ["| family | tested | active | win % | win-or-promising % | best gain | best idea |",
                  "|---|---|---|---|---|---|---|"]
        for fam, rs in sorted(fams.items(), key=lambda kv: -max(r["gain"] for r in kv[1])):
            b = max(rs, key=lambda r: r["gain"])
            lines.append(f"| {fam} | {len(rs)} | {len(act(rs))} | {rate(rs, ('win',)):.1%} | "
                         f"{rate(rs, ('win', 'promising')):.1%} | {b['gain']:+.3f} | {describe(b['idea'])} |")
        top = sorted([r for r in real if r["verdict"] in ("win", "promising")], key=lambda r: -r["gain"])[:25]
        lines += ["", "### Best 25 (win or promising)", "",
                  "| gain | verdict | sig yrs | win rate | max DD | years | idea |", "|---|---|---|---|---|---|---|"]
        for r in top:
            lines.append(f"| {r['gain']:+.3f} | {r['verdict']} | {r['years_sig']}/4 | {r['win_rate']:.1%} "
                         f"(base {r['base_win_rate']:.1%}) | {r['max_dd']:.0%} | {_fmt_years(r)} | {describe(r['idea'])} |")
        mr = [r for r in real if r["family"] in ("miner", "miner_random")]
        if mr:
            lines += ["", "### miner: do criteria learned on past trades hold the next year?", "",
                      "Win rate of the champion's trades inside the learned criteria vs outside, in the training "
                      "years and in the year after (the same trades the baseline took).", "",
                      "| idea | year | criteria found | train win in / out | next-year win in / out (n in) |",
                      "|---|---|---|---|---|"]
            for r in sorted(mr, key=lambda r: -r["gain"])[:6]:
                for k, v in r["years"].items():
                    i = v.get("rule") or {}
                    crit = "; ".join(" & ".join(f"{c[0]} in ({c[1]}, {c[2]}]" for c in reg["conds"])
                                     for reg in (i.get("regions") or [])[:2]) or i.get("why", "ML")
                    tw = (f"{i.get('train_win_in')} / {i.get('train_win_out')}" if "train_win_in" in i
                          else f"{i.get('oof_top_win')} / {i.get('oof_rest_win')}")
                    lines.append(f"| {describe(r['idea'])} | {k} | {crit[:90]} | {tw} | "
                                 f"{i.get('fwd_win_in')} / {i.get('fwd_win_out')} ({i.get('fwd_n_in')}) |")
        for fam in ("martingale", "conviction", "miner", "miner_random"):
            fr = [r for r in real if r["family"] == fam]
            fp = [r for r in plac if r["family"] == fam]
            if not fr:
                continue
            gp = sorted(r["gain"] for r in fp)
            lines += ["", f"### {fam}: {len(fr)} tested, {sum(r['gain'] > 0 for r in fr)} improve the law; "
                      f"placebos {len(fp)}, {sum(r['gain'] > 0 for r in fp)} improve"
                      + (f" (placebo best {gp[-1]:+.3f})" if gp else ""), "",
                      "| gain | verdict | max DD (base) | years | idea |", "|---|---|---|---|---|"]
            for r in sorted(fr, key=lambda r: -r["gain"])[:10]:
                lines.append(f"| {r['gain']:+.3f} | {r['verdict']} | {r['max_dd']:.0%} ({r['base_max_dd']:.0%}) | "
                             f"{_fmt_years(r)} | {describe(r['idea'])} |")
        # the operator's moving-average question: does any period stand out?
        ma = [r for r in real if r["family"] == "ma_scan"]
        if ma:
            lines += ["", "### Moving averages 2-300: gain by period bucket (best n in bucket)", "",
                      "| source tf | " + " | ".join(f"{a}-{a + 29}" for a in range(2, 300, 30)) + " |",
                      "|---|" + "---|" * 10]
            for key in sorted({(r['idea']['f']['src'], r['idea']['f']['tf']) for r in ma}):
                cells = []
                for a in range(2, 300, 30):
                    rs = [r for r in ma if (r['idea']['f']['src'], r['idea']['f']['tf']) == key
                          and a <= r['idea']['f']['n'] < a + 30]
                    if rs:
                        b = max(rs, key=lambda r: r["gain"])
                        cells.append(f"{b['gain']:+.3f} (n={b['idea']['f']['n']})")
                    else:
                        cells.append("")
                lines.append(f"| {key[0]} {key[1]} | " + " | ".join(cells) + " |")
            n37 = [r for r in ma if r["idea"]["f"]["n"] == 37]
            if n37:
                lines += ["", "Period 37 (the operator's hunch): " + "; ".join(
                    f"{r['idea']['f']['src']} {r['idea']['f']['tf']} gain {r['gain']:+.3f} ({r['verdict']})" for r in n37)]
        # plateaus: neighbouring periods that ALL help are evidence; a lone hit is luck
        scans = {}
        for r in real:
            f = r["idea"].get("f") or {}
            if (r["family"] in ("ma_scan", "rsi", "indicators", "cross_section") and "n" in f
                    and r["idea"].get("rule") == "thr" and not r["idea"].get("act")):
                scans.setdefault((f["src"], f.get("ind"), f.get("tf")), {})[int(f["n"])] = r["gain"]
        plats = []
        for key, g in scans.items():
            ns = sorted(g)
            for i in range(len(ns) - 4):
                w = ns[i:i + 5]
                if w[-1] - w[0] <= max(20, w[0]):
                    plats.append((float(min(g[n] for n in w)), key, w[0], w[-1]))
        plats.sort(key=lambda x: -x[0])
        shown = set()
        rows_p = []
        for mg, key, a, b in plats:
            if key in shown or mg <= 0:
                continue
            shown.add(key)
            rows_p.append(f"| {mg:+.3f} | {' '.join(str(x) for x in key)} | {a}-{b} |")
            if len(rows_p) >= 12:
                break
        if rows_p:
            lines += ["", "### Plateaus: five neighbouring periods that ALL help (smallest gain of the five)", "",
                      "| min gain | feature | periods |", "|---|---|---|"] + rows_p
        y24 = sorted([r for r in real if "2024" in r["years"]],
                     key=lambda r: -(law1(r["years"]["2024"]["return"], r["years"]["2024"]["max_dd"])))[:10]
        if y24:
            lines += ["", "### The ten ideas that help 2024 most (and what they do to the other years)", "",
                      "| 2024 ret/DD | all years | gain over 22-25 | idea |", "|---|---|---|---|"]
            for r in y24:
                v = r["years"]["2024"]
                lines.append(f"| {v['return']:+.1%} / {v['max_dd']:.0%} | {_fmt_years(r)} | {r['gain']:+.3f} | {describe(r['idea'])} |")
        lines.append("")
    # replication: the three checks of the journal (2026-10-16) - beats chance as a family, keeps
    # its side, holds on BOTH coin lists. Only ideas passing here are worth the operator's time.
    by: dict = {}
    for r in rows:
        if r.get("years") and not r.get("placebo_days"):
            by.setdefault(r["id"], {})[r["universe"]] = r

    def sides(r):
        """The rule's side per year; a combo's rule is a list (one per member): key by position."""
        out = set()
        for y in r["years"].values():
            rule = y.get("rule")
            parts = rule if isinstance(rule, list) else [rule]
            out.add(tuple((p or {}).get("side") for p in parts))
        return {x for x in out if any(v is not None for v in x)}
    rep = [(t["gain"] + p_["gain"], t, p_) for t, p_ in ((d.get("today"), d.get("pit")) for d in by.values())
           if t and p_ and t["verdict"] in ("win", "promising") and p_["verdict"] in ("win", "promising")
           and len(sides(t) | sides(p_)) <= 1]
    rep.sort(key=lambda x: -x[0])
    lines += ["## Replicated on both coin lists (same side every year)", ""]
    if rep:
        def robust(idea):
            """Share of the idea's neighbours tested on both lists with a positive gain on both."""
            ids = {idea_id({"family": "robust", **nb}) for nb in neighbours_of({k: v for k, v in idea.items() if k != "family"})}
            got = [by[i] for i in ids if i in by and "today" in by[i] and "pit" in by[i]]
            ok = sum(g["today"]["gain"] > 0 and g["pit"]["gain"] > 0 for g in got)
            return f"{ok}/{len(got)} of {len(ids)}" if got else f"0 tested of {len(ids)}"
        lines += ["Robust = neighbours (nearby periods, adjacent timeframes) with a positive gain on BOTH lists; "
                  "a real effect should hold on most of them.", "",
                  "| gain today | gain pit | robust | idea |", "|---|---|---|---|"]
        lines += [f"| {t['gain']:+.3f} ({t['verdict']}) | {p_['gain']:+.3f} ({p_['verdict']}) | {robust(t['idea'])} | {describe(t['idea'])} |"
                  for _, t, p_ in rep[:25]]
    else:
        lines.append("None yet.")
    lines.append("")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT


# ============================================================================ the loop

def run(hours: float, seed: int) -> int:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 10)
    except Exception:  # noqa: BLE001
        pass
    CACHE.mkdir(parents=True, exist_ok=True)
    PID.write_text(str(os.getpid()), encoding="utf-8")
    started, last_report = time.time(), 0.0
    unis = [Universe("today")]
    if PIT_CACHE.is_file():
        unis.append(Universe("pit"))
    print(f"[{now()}] rocket: universes {[u.name for u in unis]}", flush=True)
    done = {(r["universe"], r["id"]) for r in read_ledger() if not r.get("placebo_days")}
    tested: list[dict] = [r["idea"] for r in read_ledger() if not r.get("placebo_days") and "f" in r["idea"]]
    rng = random.Random(seed)
    k = 0
    for idea in ideas(seed):
        if time.time() - started > hours * 3600 or STOP.exists():
            break
        if not PIT_CACHE.is_file() or any(u.name == "pit" for u in unis):
            pass
        else:
            unis.append(Universe("pit"))
            print(f"[{now()}] rocket: point-in-time cache found - pit universe added", flush=True)
        wait_for_ram()
        iid = idea_id(idea)
        for u in unis:
            if (u.name, iid) in done:
                continue
            try:
                row = evaluate(u, idea)
            except Exception as e:  # noqa: BLE001  - one bad idea must not stop the search
                row = {"at": now(), "universe": u.name, "id": iid, "idea": idea, "family": idea.get("family"),
                       "verdict": "error", "error": repr(e)[:300], "gain": 0.0}
            done.add((u.name, iid))
            if row is None:
                row = {"at": now(), "universe": u.name, "id": iid, "idea": idea, "family": idea.get("family"),
                       "verdict": "unavailable", "gain": 0.0}
            if row["verdict"] not in ("error", "unavailable"):
                append(row)
                if "f" in idea:
                    tested.append(idea)
                print(f"[{now()}] {u.name} {row['verdict']:<9} gain {row['gain']:+.4f} "
                      f"[{row['sec']:.0f}s] {describe(idea)}", flush=True)
            else:
                append(row)
                print(f"[{now()}] {u.name} {row['verdict']} {describe(idea)} {row.get('error', '')}", flush=True)
        k += 1
        if "mg" in idea or "cv" in idea or "mine" in idea:   # sizing ideas: a placebo for EVERY one
            days = rng.randint(180, 540)
            for u in unis:
                try:
                    row = evaluate(u, idea, placebo_days=days)
                except Exception:  # noqa: BLE001
                    row = None
                if row:
                    append(row)
                    print(f"[{now()}] {u.name} placebo {row['verdict']:<9} gain {row['gain']:+.4f} {describe(idea)}", flush=True)
        if k % PLACEBO_EVERY == 0 and tested:
            p = rng.choice(tested)
            days = rng.randint(180, 540)
            for u in unis:
                try:
                    row = evaluate(u, p, placebo_days=days)
                except Exception:  # noqa: BLE001
                    row = None
                if row:
                    append(row)
                    print(f"[{now()}] {u.name} placebo {row['verdict']:<9} gain {row['gain']:+.4f} "
                          f"(shift {days} d) {describe(p)}", flush=True)
        if time.time() - last_report > REPORT_EVERY_S:
            try:
                report()
            except Exception as e:  # noqa: BLE001  - a report bug must never stop the search
                print(f"[{now()}] report failed: {e!r}", flush=True)
            last_report = time.time()
        gc.collect()
    try:
        report()
    except Exception as e:  # noqa: BLE001
        print(f"[{now()}] report failed: {e!r}", flush=True)
    return 0


def rescore() -> None:
    """Re-grade every ledger row with grade(); rows written before base_years was stored get it
    from their universe's baseline. Run only while the loop is stopped (research/rocket/STOP)."""
    rows = read_ledger()
    bases = {}
    for name in {r.get("universe") for r in rows if r.get("years") and not r.get("base_years")}:
        u = Universe(name)
        bases[name] = {str(N): {k: u.base(N)[k] for k in ("return", "max_dd", "trades", "win_rate")}
                       for N in TEST_YEARS if N in u.worlds}
    changed = 0
    for r in rows:
        if r.get("years"):
            if not r.get("base_years"):
                r["base_years"] = {k: bases[r["universe"]][k] for k in r["years"]}
            old = r.get("verdict")
            grade(r)
            changed += old != r["verdict"]
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, default=float) + chr(10) for r in rows), encoding="utf-8")
    os.replace(tmp, LEDGER)
    print(f"rescored {len(rows)} rows, {changed} verdicts changed")


# ============================================================================ the PIT cache

def pit_dump(device: str) -> Path:
    """Release 34's signals on each year's point-in-time coin list, years 2020-2025, the way
    pit.py re-books it (search.World(universe=N, cap=14), research bars only)."""
    import book_inputs as BI
    from system010_conditioned_rl import search as S
    rel = BI.release(RELEASE)
    cfg = rel["cfg"]
    CACHE.mkdir(parents=True, exist_ok=True)
    out, meta = {}, {"release": RELEASE, "cfg": cfg, "years": {}, "exit_min_hold": S.EXIT_MIN_HOLD}
    for N in ALL_YEARS:
        wait_for_ram(6.0)
        t0 = time.time()
        world = S.World(universe=N, cap=14)
        if cfg.get("features") == "full":
            world.full()
            world.x = None
        g, regime = S.gate(world, cfg)
        size = S.sizing(world, cfg)
        share, masks, keep = S.signals(world, cfg, N, g, regime, device)
        st = S.strength(world, cfg, N, g, regime, device)
        for s, d in world.per.items():
            out[f"{N}|{s}|ns"] = d["ns"]
            out[f"{N}|{s}|close"] = d["close"]
            out[f"{N}|{s}|year"] = d["year"]
            out[f"{N}|{s}|breadth"] = d["breadth"].astype(np.float32)
            out[f"{N}|{s}|size"] = size[s] if size is not None else np.ones(len(d["ns"]))
            out[f"{N}|{s}|enter"] = masks[s].astype(bool)
            out[f"{N}|{s}|keep"] = (keep[s] if keep is not None else np.ones(len(d["ns"]), bool)).astype(bool)
            out[f"{N}|{s}|strength"] = (st[s] if st is not None else np.zeros(len(d["ns"]))).astype(np.float32)
        meta["years"][N] = {"symbols": list(world.per), "share": share}
        meta["band"], meta["risk"] = world.band, world.risk
        print(f"[{now()}] pit {N}: {len(world.per)} coins, share {share} [{(time.time() - t0) / 60:.1f} min]", flush=True)
        del world, g, regime, size, masks, keep, st
        S._SIGNALS.clear()
        gc.collect()
    out["meta"] = np.array(json.dumps(meta, default=float))
    tmp = PIT_CACHE.with_name("pit_34.tmp.npz")
    np.savez_compressed(tmp, **out)
    os.replace(tmp, PIT_CACHE)
    u = Universe("pit")
    check = {str(N): u.base(N)["return"] for N in TEST_YEARS}
    print(f"[{now()}] written {PIT_CACHE}; baseline returns {check} (pit_rebook r34: 0 / +8.9 / +12.1 / +63.6 %)", flush=True)
    return PIT_CACHE


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage", choices=("run", "report", "pit-dump", "one", "rescore"))
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--idea", default=None, help="one: a JSON idea to evaluate on 'today'")
    a = ap.parse_args()
    if a.stage == "run":
        sys.exit(run(a.hours, a.seed if a.seed is not None else int(time.time()) % 100_000))
    elif a.stage == "report":
        print(report())
    elif a.stage == "rescore":
        rescore()
    elif a.stage == "pit-dump":
        pit_dump(a.device)
    else:
        print(json.dumps(evaluate(Universe("today"), json.loads(a.idea)), indent=1, default=float))
