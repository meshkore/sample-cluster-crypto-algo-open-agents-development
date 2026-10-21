"""Rocket 11 - Rocket's idea families, never tried on System 11, run against System 11's book (operator 2026-10-21:
"evaluate all possible following rocket ideas, non explored").

Base book: the System 11 law book (cap14 spot long, ranking target, MLP, configurations chosen by the operator's
law "positive every year, better toward today"), built exactly as history_v2 builds it, both seed sets.

What one test is
    idea      a rule on top of the book - a VALIDATOR (a coin may be held only while a condition holds, or may
              only be ENTERED while it holds), a market-wide GATE, or a SIZING rule (concentrate the bag on the
              coins most configurations agree on, fewer configurations, volatility targeting)
    reading   2020-2025 out of sample, both seed sets, at EQUAL RISK: the variant's 2020-25 path is rescaled to
              the base path's max drawdown, so a filter that only cuts exposure does not win by being smaller
    gain      change in the law's recency-weighted mean yearly return (weights double each year toward 2025),
              the worse of the two seed sets
    placebo   every 3rd test re-runs an earlier idea with its condition shifted in time by 4-20 months: same
              distribution, timing destroyed. A family is only interesting if it clearly beats its placebo
    2026      computed and stored for every idea, NEVER used to rank, choose or report a verdict

Writes research/plan_v2/rocket11/{ledger.jsonl, REPORT.md, status.json}. Brake: research/plan_v2/rocket11/STOP.

    python research/plan_v2/rocket11.py run --hours 24
    python research/plan_v2/rocket11.py report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

import history_v2 as H
import lab_v2 as LV
import phase3_select as P3

HERE = Path(__file__).resolve().parent
OUT = HERE / "rocket11"
CACHE = OUT / "cache"
LEDGER = OUT / "ledger.jsonl"
REPORT = OUT / "REPORT.md"
STATUS = OUT / "status.json"
STOP = OUT / "STOP"
SPEC = dict(cap=14, venue="spot_long", target="xs", feats="base", family="mlp", sel="law")
YEARS = tuple(range(2020, 2026))
PLACEBO_EVERY = 3
WIN = 0.03                                         # +3 points a year at equal risk


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Quiet:
    d: dict = {}

    def step(self, *a, **k):
        pass


# ------------------------------------------------------------------ the base book (cached)

def build_base(w) -> dict:
    """Per seed set: the unscaled bag weights 2020-2026 (law selection) and, per year, the 10 chosen
    configurations' own weights (for the sizing ideas)."""
    models = LV.FAMILY_MODELS[SPEC["family"]]
    cfgs = [dict(tf=a, h_days=b, k=c, model=d) for a, b, c, d in product(LV.INNER["tf"], LV.INNER["h_days"], LV.INNER["k"], models)]
    out = {}
    dy = H.to_daily(w, np.zeros(len(w.P4["grid"])))[1]
    for ss in ("s1", "s2"):
        seeds = P3.SEED_SETS[ss]
        cache, runs = {}, []
        for cfg in cfgs:
            pr = H.preds(w, cfg["tf"], cfg["h_days"], cfg["model"], seeds, SPEC, cache, Quiet())
            r, Wx = H.bar_returns(w, H.book(w, SPEC, cfg, pr), P3.HALF_COST, None)
            runs.append({"Wx": Wx.astype(np.float32), "d": H.to_daily(w, r)[0]})
        Wraw = np.zeros_like(w.P4["close"], dtype=np.float32)
        stack = np.zeros((H.BAG,) + Wraw.shape, dtype=np.float32)
        for N in H.BOOK_YEARS:
            py = [y for y in H.MODEL_YEARS if y < N]
            yrs = lambda d: {y: {"return": float(np.prod(1 + d[dy == y]) - 1)} for y in py}  # noqa: E731
            scored = sorted(((LV.law_score(yrs(x["d"]), py), i) for i, x in enumerate(runs)), reverse=True)[:H.BAG]
            inN = w.P4["year"] == N
            for q, (_, i) in enumerate(scored):
                stack[q][inN] = runs[i]["Wx"][inN]
            Wraw[inN] = stack[:, inN].mean(axis=0)
        out[ss] = {"W": Wraw, "stack": stack}
    return out


# ------------------------------------------------------------------ conditions (daily, causal)

class Data:
    def __init__(self, w):
        self.w = w
        P1, P4 = w.P["1d"], w.P4
        self.c1 = pd.DataFrame(P1["close"])
        self.h1, self.l1, self.v1 = pd.DataFrame(P1["high"]), pd.DataFrame(P1["low"]), pd.DataFrame(P1["usd"])
        self.mem1 = P1["member"]
        prev = np.r_[P4["grid"][0], P4["grid"][:-1]]
        self.dk = np.searchsorted(P1["grid"], prev, side="right") - 1      # daily bar known at each 4h decision
        self.days = [str((g - 1).astype("datetime64[ns]"))[:10] for g in P1["grid"]]
        jb = P1["coins"].index("BTCUSDT")
        self.btc = self.c1[jb]
        self.macro = macro_series(self.days)

    def to4h(self, D: np.ndarray) -> np.ndarray:
        """Daily (D x S or D) condition -> 4h rows, read at the last daily close before each decision."""
        D = np.asarray(D)
        k = np.clip(self.dk, 0, None)
        out = D[k]
        if D.ndim == 1:
            out = np.repeat(out[:, None], self.w.P4["close"].shape[1], axis=1)
        out = out.copy()
        out[self.dk < 0] = True
        return out

    def bc(self, s) -> np.ndarray:
        """A market-wide daily series broadcast to every coin."""
        a = np.asarray(s, dtype=float)
        return np.repeat(a[:, None], self.c1.shape[1], axis=1)


def macro_series(days: list[str]) -> dict:
    """Long daily macro history (FRED keyless CSV, alternative.me Fear & Greed, PAXG on Binance), cached a day.
    Forward-filled onto the crypto calendar, lagged one day (a US close is known the next morning)."""
    import urllib.request
    f = CACHE / "macro.json"
    if f.exists() and time.time() - f.stat().st_mtime < 86400:
        raw = json.loads(f.read_text())
    else:
        raw = {}
        ua = {"User-Agent": "quantlab-research/1.0"}
        for k, sid in {"spx": "SP500", "ndx": "NASDAQCOM", "vix": "VIXCLS", "dxy": "DTWEXBGS", "y10": "DGS10", "y2": "DGS2",
                       "oil": "DCOILWTICO", "walcl": "WALCL", "tga": "WTREGEN", "rrp": "RRPONTSYD", "hy": "BAMLH0A0HYM2"}.items():
            try:
                txt = urllib.request.urlopen(urllib.request.Request(
                    f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=2017-06-01", headers=ua), timeout=60).read().decode()
                raw[k] = [[d, float(v)] for d, v in (ln.split(",") for ln in txt.strip().splitlines()[1:]) if v not in (".", "")]
            except Exception as exc:  # noqa: BLE001
                print(f"macro {k}: {exc}", flush=True)
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request("https://api.alternative.me/fng/?limit=0", headers=ua), timeout=60).read())
            raw["fg"] = sorted([[datetime.fromtimestamp(int(x["timestamp"]), timezone.utc).strftime("%Y-%m-%d"), float(x["value"])] for x in d["data"]])
        except Exception as exc:  # noqa: BLE001
            print(f"macro fg: {exc}", flush=True)
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(raw))
    out = {}
    for k, ser in raw.items():
        mp, last, vals = dict(ser), np.nan, []
        for d in days:
            last = mp.get(d, last)
            vals.append(last)
        out[k] = np.r_[np.nan, np.array(vals[:-1], dtype=float)]          # one-day lag
    if all(k in out for k in ("walcl", "tga", "rrp")):
        out["netliq"] = out["walcl"] / 1000 - out["tga"] / 1000 - out["rrp"]
    return out


def ind(D: Data, kind: str, n: int, src: str = "coin") -> pd.DataFrame:
    """A daily indicator frame (days x coins)."""
    c = D.c1 if src == "coin" else pd.DataFrame(np.repeat(D.btc.values[:, None], D.c1.shape[1], axis=1))
    if kind == "sma_dist":
        return c / c.rolling(n, min_periods=max(2, n // 2)).mean() - 1
    if kind == "ema_dist":
        return c / c.ewm(span=n, adjust=False, min_periods=max(2, n // 2)).mean() - 1
    if kind == "roc":
        return c / c.shift(n) - 1
    if kind == "rsi":
        d = c.diff()
        up, dn = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
        return 100 - 100 / (1 + up / (dn + 1e-12))
    if kind == "vol":
        return np.log(c).diff().rolling(n, min_periods=max(3, n // 2)).std()
    if kind == "volratio":
        lr = np.log(c).diff()
        return lr.rolling(n).std() / (lr.rolling(4 * n).std() + 1e-12)
    if kind == "dd":
        return c / c.rolling(n, min_periods=2).max() - 1
    if kind == "rangepos":
        hi, lo = c.rolling(n).max(), c.rolling(n).min()
        return (c - lo) / (hi - lo + 1e-12)
    if kind == "volz":
        lv = np.log(D.v1.replace(0, np.nan))
        return (lv - lv.rolling(n).mean()) / (lv.rolling(n).std() + 1e-9)
    if kind == "xrank_roc":
        r = c / c.shift(n) - 1
        return pd.DataFrame(np.where(D.mem1, r, np.nan)).rank(axis=1, pct=True)
    if kind == "macd":
        f, s = c.ewm(span=max(2, n // 2), adjust=False).mean(), c.ewm(span=n, adjust=False).mean()
        m = f - s
        return (m - m.ewm(span=9, adjust=False).mean()) / c
    raise ValueError(kind)


# ------------------------------------------------------------------ ideas

KINDS = {"sma_dist": (0.0,), "ema_dist": (0.0,), "roc": (0.0,), "rsi": (30, 50, 70, 80), "vol": None, "volratio": (0.8, 1.0, 1.25, 1.5),
         "dd": (-0.1, -0.2, -0.3, -0.5), "rangepos": (0.2, 0.5, 0.8), "volz": (-1.0, 0.0, 1.0, 2.0), "xrank_roc": (0.3, 0.5, 0.7), "macd": (0.0,)}
PERIODS = (3, 5, 7, 10, 14, 20, 30, 50, 75, 100, 150, 200, 300)


def gen_idea(rng: random.Random) -> dict:
    fam = rng.choice(["coin", "coin", "coin", "btc", "market", "macro", "macro", "sizing", "sizing", "combo"])
    if fam == "coin" or fam == "btc":
        kind = rng.choice([k for k in KINDS if not (fam == "btc" and k in ("xrank_roc", "volz"))])
        n = rng.choice(PERIODS)
        th = KINDS[kind]
        t = rng.choice(th) if th else None
        if kind == "vol":
            t = rng.choice((0.25, 0.5, 0.75))       # quantile of the coin's own past (expanding)
        return {"family": f"{fam}:{kind}", "kind": kind, "n": n, "t": t, "side": rng.choice(["above", "below"]),
                "src": "btc" if fam == "btc" else "coin", "mode": rng.choice(["hold", "entry"])}
    if fam == "market":
        kind = rng.choice(["breadth", "dispersion", "mkt_roc"])
        n = rng.choice((10, 20, 50, 100))
        t = {"breadth": rng.choice((0.3, 0.5, 0.7)), "dispersion": rng.choice((0.25, 0.5, 0.75)), "mkt_roc": rng.choice((-0.1, 0.0, 0.1))}[kind]
        return {"family": f"market:{kind}", "kind": kind, "n": n, "t": t, "side": rng.choice(["above", "below"]), "mode": "hold"}
    if fam == "macro":
        k = rng.choice(["spx", "ndx", "vix", "dxy", "y10", "y2", "curve", "oil", "netliq", "hy", "fg"])
        how = rng.choice(["level_q", "chg"]) if k not in ("vix", "fg", "hy") else rng.choice(["level_q", "chg", "level"])
        n = rng.choice((5, 10, 20, 60))
        t = rng.choice((0.2, 0.5, 0.8)) if how == "level_q" else rng.choice((0.0,)) if how == "chg" else \
            {"vix": rng.choice((15, 20, 25, 30)), "fg": rng.choice((20, 25, 50, 75, 80)), "hy": rng.choice((3.0, 4.0, 5.0))}[k]
        return {"family": f"macro:{k}", "key": k, "how": how, "n": n, "t": t, "side": rng.choice(["above", "below"]), "mode": "hold"}
    if fam == "sizing":
        kind = rng.choice(["consensus", "bag", "voltarget", "topk"])
        if kind == "consensus":
            return {"family": "sizing:consensus", "kind": kind, "m": rng.choice((2, 3, 4, 5, 6))}
        if kind == "bag":
            return {"family": "sizing:bag", "kind": kind, "m": rng.choice((1, 2, 3, 5))}
        if kind == "topk":
            return {"family": "sizing:topk", "kind": kind, "m": rng.choice((1, 2, 3, 4, 5))}
        return {"family": "sizing:voltarget", "kind": kind, "n": rng.choice((10, 20, 60)), "t": rng.choice((0.4, 0.6, 0.8))}
    best = top_singles(25)
    if len(best) < 4:
        return gen_idea(rng)
    a, b = rng.sample(best, 2)
    return {"family": "combo", "kind": "and", "parts": [a, b]}


def idea_id(idea: dict) -> str:
    return hashlib.md5(json.dumps(idea, sort_keys=True).encode()).hexdigest()[:12]


def cond(D: Data, idea: dict, shift: int = 0) -> np.ndarray | None:
    """Daily boolean 'allowed' (days x coins); `shift` days later in time for the placebo."""
    f = idea["family"]
    if idea.get("kind") == "and":
        a, b = cond(D, idea["parts"][0], shift), cond(D, idea["parts"][1], shift)
        return None if a is None or b is None else (a & b)
    if f.startswith("coin:") or f.startswith("btc:"):
        X = ind(D, idea["kind"], idea["n"], idea["src"]).values
        t = idea["t"]
        if idea["kind"] == "vol":
            t = pd.DataFrame(X).expanding(min_periods=60).quantile(idea["t"]).values
    elif f.startswith("market:"):
        c = D.c1
        if idea["kind"] == "breadth":
            above = (c > c.rolling(idea["n"], min_periods=idea["n"] // 2).mean()).values & D.mem1
            X = D.bc(above.sum(axis=1) / np.maximum(D.mem1.sum(axis=1), 1))
        elif idea["kind"] == "dispersion":
            r = (c / c.shift(idea["n"]) - 1).where(D.mem1)
            sd = r.std(axis=1)
            X = D.bc(sd.values)
            t = None
            X = D.bc((sd > sd.expanding(min_periods=100).quantile(idea["t"])).values.astype(float))
            idea = {**idea, "t_eff": 0.5}
        else:
            r = (c / c.shift(idea["n"]) - 1).where(D.mem1)
            X = D.bc(r.mean(axis=1).values)
        t = idea.get("t_eff", idea["t"])
    elif f.startswith("macro:"):
        k = idea["key"]
        s = (D.macro.get("y10", None) - D.macro.get("y2", None)) if k == "curve" and "y10" in D.macro and "y2" in D.macro else D.macro.get(k)
        if s is None or np.isfinite(s).sum() < 300:
            return None
        s = pd.Series(s).ffill()
        if idea["how"] == "chg":
            x = s - s.shift(idea["n"]) if k in ("vix", "y10", "y2", "curve", "fg", "hy") else s / s.shift(idea["n"]) - 1
            t = idea["t"]
        elif idea["how"] == "level_q":
            x = s
            t = s.expanding(min_periods=250).quantile(idea["t"]).values
        else:
            x, t = s, idea["t"]
        X = D.bc(x.values)
        if not np.isscalar(t):
            t = D.bc(t)
    else:
        return None
    with np.errstate(invalid="ignore"):
        ok = (X > t) if idea["side"] == "above" else (X < t)
        ok = ok | ~np.isfinite(X)                                     # no reading never blocks
    if shift:
        ok = np.r_[np.ones((shift, ok.shape[1]), dtype=bool), ok[:-shift]]
    return ok


def apply(D: Data, base: dict, idea: dict, shift: int = 0) -> np.ndarray | None:
    W, stack = base["W"], base["stack"]
    f = idea["family"]
    if f.startswith("sizing:"):
        k = idea["kind"]
        if k == "consensus":                      # only the coins >= m configurations hold; keep the bag's exposure
            votes = (stack > 1e-9).sum(axis=0)
            keep = votes >= idea["m"]
            Wk = np.where(keep, W, 0.0)
            tot, kt = W.sum(axis=1, keepdims=True), Wk.sum(axis=1, keepdims=True)
            return np.where(kt > 0, Wk * tot / np.maximum(kt, 1e-12), 0.0)
        if k == "bag":                            # only the best m configurations of the year
            return stack[: idea["m"]].mean(axis=0)
        if k == "topk":                           # the m coins with the most votes (ties by weight), equal weight of the exposure
            votes = (stack > 1e-9).sum(axis=0) + W / (W.max() + 1e-12)
            order = np.argsort(-votes, axis=1)[:, : idea["m"]]
            M = np.zeros_like(W, dtype=bool)
            np.put_along_axis(M, order, True, axis=1)
            M &= W > 1e-9
            tot, n = W.sum(axis=1, keepdims=True), M.sum(axis=1, keepdims=True)
            return np.where(M, tot / np.maximum(n, 1), 0.0)
        if k == "voltarget":                      # scale the whole book to a target of its own past volatility
            r, _ = H.bar_returns(D.w, W, P3.HALF_COST, None)
            sd = pd.Series(r).rolling(idea["n"] * 6, min_periods=30).std().shift(1).values
            tgt = pd.Series(sd).expanding(min_periods=500).quantile(idea["t"]).values     # the past only
            ok = np.isfinite(sd) & (sd > 0) & np.isfinite(tgt)
            m = np.where(ok, np.clip(tgt / np.where(ok, sd, 1.0), 0.25, 2.0), 1.0)
            return W * m[:, None]
        return None
    ok = cond(D, idea, shift)
    if ok is None:
        return None
    A = D.to4h(ok)
    if idea.get("mode") == "entry":               # may only be ENTERED while allowed; a held coin stays
        held = W > 1e-9
        out = np.zeros_like(W)
        was = np.zeros(W.shape[1], dtype=bool)
        for i in range(W.shape[0]):
            now_ = held[i] & (A[i] | was)
            out[i] = np.where(now_, W[i], 0.0)
            was = now_
        return out
    return np.where(A, W, 0.0)


# ------------------------------------------------------------------ scoring

def yearly(w, W) -> tuple[dict, float, np.ndarray, np.ndarray]:
    r, _ = H.bar_returns(w, W, P3.HALF_COST, None)
    d, dy, _ = H.to_daily(w, r)
    return d, dy


def law_mean(rets: list[float]) -> float:
    wts = [2.0 ** i for i in range(len(rets))]
    return float(np.dot(rets, wts) / sum(wts))


def score(w, W, ref_dd: float | None = None) -> dict:
    d, dy = yearly(w, W)
    res = d[np.isin(dy, YEARS)]
    eq = np.cumprod(1 + res)
    dd = float((1 - eq / np.maximum.accumulate(eq)).max()) if len(eq) else 0.0
    k = min(3.0, ref_dd / dd) if ref_dd and dd > 0 else 1.0          # equal risk: rescale to the base's 2020-25 DD
    d = d * k
    yr = {int(y): float(np.prod(1 + d[dy == y]) - 1) for y in YEARS}
    fw = d[dy == 2026]
    return {"years": {y: round(v, 4) for y, v in yr.items()}, "law": round(law_mean([yr[y] for y in YEARS]), 4),
            "pos": sum(v > 0 for v in yr.values()), "dd": round(dd, 4), "k": round(k, 3),
            "sharpe": round(float(res.mean() / (res.std() + 1e-12) * np.sqrt(365)), 3),
            "y2026": round(float(np.prod(1 + fw) - 1), 4) if len(fw) else None}


# ------------------------------------------------------------------ loop

def ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(x) for x in LEDGER.read_text(encoding="utf-8").splitlines() if x.strip()]


_TOP: list = []


def top_singles(n: int) -> list[dict]:
    return _TOP[:n]


def refresh_top(rows: list[dict]) -> None:
    real = [r for r in rows if not r.get("placebo") and r["idea"].get("kind") != "and" and not r["idea"]["family"].startswith("sizing")]
    _TOP[:] = [r["idea"] for r in sorted(real, key=lambda r: -r["gain"])[:40]]


def verdict(g: float, sv: dict, base: dict) -> str:
    worse_pos = min(s["pos"] for s in sv.values())
    if g >= WIN and worse_pos >= base["pos"]:
        return "win"
    if g >= WIN / 3:
        return "promising"
    if g > -WIN / 3:
        return "neutral"
    return "hurts"


def run(hours: float) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "run.pid").write_text(str(os.getpid()))
    cut = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "ns").astype("int64")
    w = H.world(SPEC["cap"], int(cut))
    fb = CACHE / "base.npz"
    CACHE.mkdir(parents=True, exist_ok=True)
    if fb.exists() and time.time() - fb.stat().st_mtime < 7 * 86400:
        z = np.load(fb)
        base = {ss: {"W": z[f"{ss}_W"], "stack": z[f"{ss}_stack"]} for ss in ("s1", "s2")}
        if base["s1"]["W"].shape != w.P4["close"].shape:
            base = None
    else:
        base = None
    if base is None:
        print(f"[{now()}] building the base book (both seed sets)", flush=True)
        base = build_base(w)
        np.savez(fb, **{f"{ss}_{k}": v for ss, b in base.items() for k, v in b.items()})
    D = Data(w)
    ref = {ss: score(w, base[ss]["W"]) for ss in base}
    print(f"[{now()}] base: " + " | ".join(f"{ss} law {r['law']:+.3f} pos {r['pos']}/6 DD {r['dd']:.0%}" for ss, r in ref.items()), flush=True)
    rows = ledger()
    seen = {r["id"] for r in rows}
    refresh_top(rows)
    rng = random.Random(int(time.time()))
    t0, n = time.time(), 0
    while time.time() - t0 < hours * 3600 and not STOP.exists():
        n += 1
        placebo = n % PLACEBO_EVERY == 0 and len(rows) > 30
        if placebo:
            src = rng.choice([r for r in rows if not r.get("placebo") and not r["idea"]["family"].startswith("sizing")])
            idea, shift = src["idea"], rng.randint(120, 600)
            iid = f"{src['id']}~p{shift}"
        else:
            idea, shift = gen_idea(rng), 0
            iid = idea_id(idea)
            if iid in seen:
                continue
        try:
            sv = {}
            for ss in base:
                Wv = apply(D, base[ss], idea, shift)
                if Wv is None:
                    raise ValueError("no data")
                sv[ss] = score(w, Wv, ref[ss]["dd"])
        except Exception as exc:  # noqa: BLE001
            print(f"skip {idea.get('family')}: {exc}", flush=True)
            seen.add(iid)
            continue
        gains = {ss: sv[ss]["law"] - ref[ss]["law"] for ss in sv}
        g = min(gains.values())
        row = {"id": iid, "at": now(), "idea": idea, "placebo": bool(placebo), "shift_days": shift or None, "gain": round(g, 4),
               "gains": {k: round(v, 4) for k, v in gains.items()}, "verdict": verdict(g, sv, min(ref.values(), key=lambda r: r["pos"])),
               "seeds": sv}
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        rows.append(row)
        seen.add(iid)
        if n % 25 == 0:
            refresh_top(rows)
            report(rows, ref)
    report(rows, ref)
    return 0


def report(rows: list[dict] | None = None, ref: dict | None = None) -> None:
    rows = rows if rows is not None else ledger()
    real = [r for r in rows if not r.get("placebo")]
    plac = [r for r in rows if r.get("placebo")]
    rate = lambda rs, vs=("win",): (sum(r["verdict"] in vs for r in rs) / len(rs)) if rs else 0.0  # noqa: E731
    fams = {}
    for r in real:
        fams.setdefault(r["idea"]["family"].split(":")[0], []).append(r)
    pf = {}
    for r in plac:
        pf.setdefault(r["idea"]["family"].split(":")[0], []).append(r)
    p0 = rate(plac, ("win", "promising"))
    p1 = rate(real, ("win", "promising"))
    nreal = max(len(real), 1)
    z = (p1 - p0) / np.sqrt(max(p0 * (1 - p0), 1e-6) / nreal) if plac else 0.0
    L = [f"# Rocket 11 - report ({now()})", "",
         "Rocket's idea families on System 11's law book (cap14 spot long, MLP, law selection). Gain = change in the law's "
         "recency-weighted mean yearly return 2020-2025 at EQUAL RISK (each variant rescaled to the base's max DD), the worse "
         "of two seed sets. Placebo = the same idea shifted 4-20 months. 2026 is stored but never used to rank.", ""]
    if ref:
        L += ["Base: " + " · ".join(f"{ss}: law {r['law']:+.3f}, {r['pos']}/6 years positive, DD {r['dd']:.0%}, "
                                     + " ".join(f"{y}:{v:+.0%}" for y, v in r['years'].items()) for ss, r in ref.items()), ""]
    L += [f"**Ideas tested: {len(real)} real, {len(plac)} placebo. Win-or-promising: real {p1:.1%} vs placebo {p0:.1%} (z = {z:+.1f}). "
          "A z above +3 would be evidence; below, the 'winners' are what chance produces.**", "",
          "| family | real | win | promising | placebo | placebo w/p | best gain | best idea |", "|---|---|---|---|---|---|---|---|"]
    for fam, rs in sorted(fams.items(), key=lambda kv: -max(r["gain"] for r in kv[1])):
        b = max(rs, key=lambda r: r["gain"])
        L.append(f"| {fam} | {len(rs)} | {sum(r['verdict'] == 'win' for r in rs)} | {sum(r['verdict'] == 'promising' for r in rs)} | "
                 f"{len(pf.get(fam, []))} | {rate(pf.get(fam, []), ('win', 'promising')):.0%} | {b['gain']:+.3f} | `{describe(b['idea'])}` |")
    L += ["", "## Best 20 real ideas (2026 shown for information only)", "",
          "| gain | verdict | " + " | ".join(str(y) for y in YEARS) + " | DD | 2026 | idea |", "|---|---|" + "---|" * len(YEARS) + "---|---|---|"]
    for r in sorted(real, key=lambda r: -r["gain"])[:20]:
        s = min(r["seeds"].values(), key=lambda x: x["law"])
        L.append(f"| {r['gain']:+.3f} | {r['verdict']} | " + " | ".join(f"{s['years'][str(y)] if str(y) in s['years'] else s['years'][y]:+.0%}" for y in YEARS)
                 + f" | {s['dd']:.0%} | {(s['y2026'] or 0):+.1%} | `{describe(r['idea'])}` |")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    STATUS.write_text(json.dumps({"at": now(), "real": len(real), "placebo": len(plac), "rate_real": round(p1, 4), "rate_placebo": round(p0, 4),
                                  "z": round(float(z), 2), "best": [{"gain": r["gain"], "verdict": r["verdict"], "idea": describe(r["idea"])}
                                                                    for r in sorted(real, key=lambda r: -r["gain"])[:10]]}), encoding="utf-8")


def describe(idea: dict) -> str:
    f = idea["family"]
    if idea.get("kind") == "and":
        return " AND ".join(describe(p) for p in idea["parts"])
    if f.startswith("sizing:"):
        return f"{f} " + " ".join(f"{k}={v}" for k, v in idea.items() if k not in ("family", "kind"))
    if f.startswith("macro:"):
        return f"{idea['mode']} while {idea['key']} {idea['how']}{'' if idea['how'] == 'level' else ' n=' + str(idea['n'])} {idea['side']} {idea['t']}"
    return f"{idea.get('mode', 'hold')} while {idea.get('src', 'mkt')} {idea['kind']} n={idea['n']} {idea['side']} {idea['t']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("run", "report"))
    ap.add_argument("--hours", type=float, default=24)
    a = ap.parse_args()
    if a.stage == "report":
        report()
        return 0
    return run(a.hours)


if __name__ == "__main__":
    raise SystemExit(main())
