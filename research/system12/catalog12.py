"""System 12 - the strategy catalogue (operator 2026-10-22: "locate the thousand best strategies, test them one by one,
keep them well indexed so we do not repeat ourselves").

    catalog/raw/<family>.jsonl   what the collectors found (format: catalog/SPEC.md), one strategy per line
    catalog/results.jsonl        one verdict per tested strategy (append only; a strategy is never tested twice)
    catalog/CATALOG.md           the index: every strategy, its source, and its verdict

Each implementable strategy is evaluated the same way:
    daily signals at the close (only the SPEC vocabulary, parsed by a whitelist - never eval of free text),
    traded from the next 4h bar on USD-M perpetuals (0.10%/side + impact, funding charged), 40% volatility target,
    each parameter combination's choice for year N made on 2019..N-1 (walk-forward), read on N. 2026 is read only.
Verdict:
    A  beats System 12's frozen book (2021-25 per year > its +23.5%) with the chain drawdown <= 40%
    B  positive in >= 4 of 5 years 2021-25 with drawdown <= 40%    (a candidate to combine with System 12)
    C  neither

    python research/system12/catalog12.py          tests every new implementable strategy, rewrites CATALOG.md
"""

from __future__ import annotations

import ast
import itertools
import json
import operator
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import system12_ls as L

HERE = Path(__file__).resolve().parent
CAT = HERE / "catalog"
RES = CAT / "results.jsonl"
READ = (2021, 2022, 2023, 2024, 2025)
FWD = 2026
FROZEN_ANN = 0.235
MAX_DD = 0.40
HALVINGS = np.array(["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20"], dtype="datetime64[D]")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- indicators (pandas Series in, Series out)

def S(x):
    return x if isinstance(x, pd.Series) else pd.Series(x)


def sma(x, n): return S(x).rolling(int(n), min_periods=int(n)).mean()
def ema(x, n): return S(x).ewm(span=int(n), adjust=False, min_periods=int(n)).mean()
def wma(x, n):
    w = np.arange(1, int(n) + 1)
    return S(x).rolling(int(n), min_periods=int(n)).apply(lambda a: (a * w).sum() / w.sum(), raw=True)
def highest(x, n, lag=0): return S(x).shift(int(lag)).rolling(int(n), min_periods=int(n)).max()
def lowest(x, n, lag=0): return S(x).shift(int(lag)).rolling(int(n), min_periods=int(n)).min()
def shift(x, n): return S(x).shift(int(n))
def roc(x, n): return S(x) / S(x).shift(int(n)) - 1
def stdev(x, n): return S(x).rolling(int(n), min_periods=int(n)).std()
def zscore(x, n): return (S(x) - sma(x, n)) / stdev(x, n)
def rsi(x, n):
    d = S(x).diff()
    up = d.clip(lower=0).ewm(alpha=1 / int(n), adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / int(n), adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))
def macd(x, f, s): return ema(x, f) - ema(x, s)
def macd_signal(x, f, s, g): return ema(macd(x, f, s), g)
def realized_vol(n): return stdev(np.log(V["close"]).diff(), n) * np.sqrt(365)
def bb_up(x, n, k): return sma(x, n) + k * stdev(x, n)
def bb_lo(x, n, k): return sma(x, n) - k * stdev(x, n)
def abs_(x): return S(x).abs()
def min_(a, b): return np.minimum(S(a), S(b))
def max_(a, b): return np.maximum(S(a), S(b))
def cross_above(a, b): a, b = S(a), S(b); return (a > b) & (a.shift(1) <= b.shift(1))
def cross_below(a, b): a, b = S(a), S(b); return (a < b) & (a.shift(1) >= b.shift(1))


def _tr():
    h, l, c = V["high"], V["low"], V["close"]
    return pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)


def atr(n): return _tr().ewm(alpha=1 / int(n), adjust=False, min_periods=int(n)).mean()
def kc_up(n, k): return ema(V["close"], n) + k * atr(n)
def kc_lo(n, k): return ema(V["close"], n) - k * atr(n)


def _dm(n):
    h, l = V["high"], V["low"]
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0))
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0))
    a = atr(n)
    return (100 * pdm.ewm(alpha=1 / int(n), adjust=False).mean() / a, 100 * mdm.ewm(alpha=1 / int(n), adjust=False).mean() / a)


def plus_di(n): return _dm(n)[0]
def minus_di(n): return _dm(n)[1]
def adx(n):
    p, m = _dm(n)
    dx = 100 * (p - m).abs() / (p + m).replace(0, np.nan)
    return dx.ewm(alpha=1 / int(n), adjust=False).mean()
def stoch_k(n): return 100 * (V["close"] - lowest(V["low"], n)) / (highest(V["high"], n) - lowest(V["low"], n)).replace(0, np.nan)
def stoch_d(n, m): return sma(stoch_k(n), m)
def cci(n):
    tp = (V["high"] + V["low"] + V["close"]) / 3
    md = tp.rolling(int(n)).apply(lambda a: np.abs(a - a.mean()).mean(), raw=True)
    return (tp - sma(tp, n)) / (0.015 * md)
def willr(n): return -100 * (highest(V["high"], n) - V["close"]) / (highest(V["high"], n) - lowest(V["low"], n)).replace(0, np.nan)
def mfi(n):
    tp = (V["high"] + V["low"] + V["close"]) / 3
    mf = tp * V["volume"]
    pos = mf.where(tp > tp.shift(1), 0.0).rolling(int(n)).sum()
    neg = mf.where(tp < tp.shift(1), 0.0).rolling(int(n)).sum()
    return 100 - 100 / (1 + pos / neg.replace(0, np.nan))
def obv(): return (np.sign(V["close"].diff()).fillna(0) * V["volume"]).cumsum()
def vwap(n): return (V["close"] * V["volume"]).rolling(int(n)).sum() / V["volume"].rolling(int(n)).sum()


def supertrend_dir(n, k):
    a, c = atr(n).values, V["close"].values
    hl2 = ((V["high"] + V["low"]) / 2).values
    up, dn = hl2 - k * a, hl2 + k * a
    d, fu, fd = np.ones(len(c)), up.copy(), dn.copy()
    for t in range(1, len(c)):
        fu[t] = max(up[t], fu[t - 1]) if c[t - 1] > fu[t - 1] else up[t]
        fd[t] = min(dn[t], fd[t - 1]) if c[t - 1] < fd[t - 1] else dn[t]
        d[t] = 1 if c[t] > fd[t - 1] else (-1 if c[t] < fu[t - 1] else d[t - 1])
    return pd.Series(np.where(np.isfinite(a), d, 0))


def psar_dir(step, mx):
    h, l = V["high"].values, V["low"].values
    d, sar, ep, af = np.ones(len(h)), l[0], h[0], step
    up = True
    for t in range(1, len(h)):
        sar = sar + af * (ep - sar)
        if up:
            if l[t] < sar:
                up, sar, ep, af = False, ep, l[t], step
            elif h[t] > ep:
                ep, af = h[t], min(af + step, mx)
        else:
            if h[t] > sar:
                up, sar, ep, af = True, ep, h[t], step
            elif l[t] < ep:
                ep, af = l[t], min(af + step, mx)
        d[t] = 1 if up else -1
    return pd.Series(d)


def ichi_tenkan(): return (highest(V["high"], 9) + lowest(V["low"], 9)) / 2
def ichi_kijun(): return (highest(V["high"], 26) + lowest(V["low"], 26)) / 2
def ichi_span_a(): return ((ichi_tenkan() + ichi_kijun()) / 2).shift(26)
def ichi_span_b(): return ((highest(V["high"], 52) + lowest(V["low"], 52)) / 2).shift(26)


FUNCS = {f: globals()[f] for f in ("sma ema wma highest lowest shift roc zscore stdev rsi macd macd_signal atr adx plus_di minus_di "
                                   "stoch_k stoch_d cci willr mfi obv bb_up bb_lo kc_up kc_lo supertrend_dir psar_dir ichi_tenkan "
                                   "ichi_kijun ichi_span_a ichi_span_b vwap realized_vol cross_above cross_below").split()}
FUNCS.update({"abs": abs_, "min": min_, "max": max_})
V: dict = {}                                                       # the current asset's variables (set by Book.series)

BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.BitAnd: operator.and_, ast.BitOr: operator.or_}
CMP = {ast.Lt: operator.lt, ast.Gt: operator.gt, ast.LtE: operator.le, ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}


def _b(x):
    return S(x).fillna(0).astype(bool) if not isinstance(x, (int, float)) else bool(x)


def evaluate(expr: str, params: dict):
    """Whitelisted evaluation: names from the vocabulary or params, calls to FUNCS, arithmetic, comparisons, & | ~."""
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name):
            if n.id in params:
                return params[n.id]
            if n.id in V:
                return V[n.id]
            raise ValueError(f"unknown name {n.id}")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS and not n.keywords:
            return FUNCS[n.func.id](*[ev(a) for a in n.args])
        if isinstance(n, ast.BinOp) and type(n.op) in BIN:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, (ast.BitAnd, ast.BitOr)):
                a, b = _b(a), _b(b)
            return BIN[type(n.op)](a, b)
        if isinstance(n, ast.BoolOp):
            vals = [_b(ev(v)) for v in n.values]
            out = vals[0]
            for v in vals[1:]:
                out = (out & v) if isinstance(n.op, ast.And) else (out | v)
            return out
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            if isinstance(n.op, (ast.Invert, ast.Not)):
                return ~_b(v)
            if isinstance(n.op, ast.USub):
                return -v
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in CMP:
            return CMP[type(n.ops[0])](ev(n.left), ev(n.comparators[0]))
        raise ValueError(f"not allowed: {ast.dump(n)[:80]}")
    expr = expr.replace("&&", "&").replace("||", "|")
    return ev(ast.parse(expr, mode="eval"))


def latch(entry, exit_) -> np.ndarray:
    e, x = _b(entry).values, _b(exit_).values
    s, st = np.zeros(len(e)), 0.0
    for t in range(len(e)):
        if e[t]:
            st = 1.0
        elif x[t]:
            st = 0.0
        s[t] = st
    return s


def with_stops(pos, close, sl, tp):
    if not sl and not tp:
        return pos
    out, entry = pos.copy(), None
    for t in range(len(pos)):
        if pos[t] == 0:
            entry = None
            continue
        if entry is None or (t > 0 and pos[t - 1] == 0):
            entry, stopped = close[t], False
        if stopped:
            out[t] = 0
            continue
        r = (close[t] / entry - 1) * np.sign(pos[t])
        if (sl and r < -sl) or (tp and r > tp):
            stopped = True
    return out


# ---------------------------------------------------------------- the book

class Book:
    def __init__(self):
        self.eng, _ = L.setup()
        e, w, ctx = self.eng, self.eng.w, self.eng.ctx
        self.ctx, self.w = ctx, w
        P = w.P["1d"]
        days = np.array([str((g - 1).astype("datetime64[ns]"))[:10] for g in P["grid"]], dtype="datetime64[D]")
        self.days = days
        f4 = w.fund4[:, ctx.jb]
        di = np.clip(np.searchsorted(P["grid"], w.P4["grid"], side="left"), 0, ctx.nD - 1)
        fd = pd.Series(np.nan_to_num(f4)).groupby(di).sum()
        fdaily = pd.Series(np.zeros(ctx.nD))
        fdaily[fd.index] = fd.values
        mac = {k: pd.Series(v) for k, v in L.R.macro_series([str(d) for d in days]).items()}
        dt = pd.to_datetime(days.astype(str))
        last_halving = HALVINGS[np.clip(np.searchsorted(HALVINGS, days, side="right") - 1, 0, None)]
        self.common = {
            "btc_close": pd.Series(P["close"][:, ctx.jb]), "eth_close": pd.Series(P["close"][:, ctx.je]),
            "funding_7d": fdaily.shift(1).rolling(7).sum(),
            "fear_greed": mac.get("fg"), "vix": mac.get("vix"), "spx": mac.get("spx"), "ndx": mac.get("ndx"),
            "dxy": mac.get("dxy"), "us2y": mac.get("y2"), "netliq": mac.get("netliq"),
            "dow": pd.Series(dt.dayofweek), "dom": pd.Series(dt.day), "month": pd.Series(dt.month),
            "days_to_month_end": pd.Series((dt + pd.offsets.MonthEnd(0) - dt).days),
            "days_since_halving": pd.Series((days - last_halving).astype(int)),
        }
        self.P = P
        self.ix = {"BTC": ctx.jb, "ETH": ctx.je}
        self.vt = {k: e.vt_factor(k, 0.4) for k in ("BTC", "BTC+ETH")}
        self.dy = e.dy
        self.b4 = {"BTC": e.b4["BTC"]}

    def series(self, coin):
        j = self.ix[coin]
        P = self.P
        V.clear()
        V.update(self.common)
        V.update({"open": pd.Series(P["open"][:, j]), "high": pd.Series(P["high"][:, j]), "low": pd.Series(P["low"][:, j]),
                  "close": pd.Series(P["close"][:, j]), "volume": pd.Series(P["usd"][:, j]),
                  "taker_ratio": pd.Series(P["taker"][:, j] / np.where(P["usd"][:, j] > 0, P["usd"][:, j], np.nan))})

    def position(self, st, coin, p):
        self.series(coin)
        pos = latch(evaluate(st["long_entry"], p), evaluate(st["long_exit"], p)) if st.get("long_entry") else np.zeros(self.ctx.nD)
        if st.get("short_entry"):
            sh = latch(evaluate(st["short_entry"], p), evaluate(st.get("short_exit") or "close < 0", p))
            pos = np.where((pos > 0) & (sh > 0), 0.0, pos - sh)
        return with_stops(pos, V["close"].values, st.get("stop_loss"), st.get("take_profit"))

    def weights(self, st, p):
        coins = {"BTC": ["BTC"], "ETH": ["ETH"], "BTCETH": ["BTC", "ETH"]}[st.get("asset", "BTC")]
        vt = self.vt["BTC" if coins == ["BTC"] else "BTC+ETH"]
        W = 0
        for c in coins:
            d = self.position(st, c, p) * vt / len(coins)
            col = np.zeros(self.b4["BTC"].shape[1])
            col[self.ix[c]] = 1.0
            W = W + self.eng.to4(d)[:, None] * col[None, :]
        return np.where(self.eng.can, W, 0.0)

    def daily(self, W):
        return self.eng.daily_ls(W)


def combos(params: dict) -> list[dict]:
    keys = list(params or {})
    vals = [list(v)[:3] if isinstance(v, (list, tuple)) else [v] for v in (params or {}).values()]
    return [dict(zip(keys, c)) for c in itertools.product(*vals)] or [{}]


def test(book: Book, st: dict) -> dict:
    cs = combos(st.get("params"))[:27]
    ds = [book.daily(book.weights(st, p)) for p in cs]
    yrs, chosen, chain = {}, {}, []
    for N in READ + (FWD,):
        train = tuple(range(2019, N))
        obj = [L.B.objective_value(d, book.dy, train)[0] for d in ds]
        k = int(np.nanargmax(obj)) if np.isfinite(obj).any() else 0
        yrs[N] = round(L.B.yearly(ds[k], book.dy, (N,))[N], 4)
        chosen[N] = cs[k]
        if N in READ:
            chain.append(ds[k][book.dy == N])
    dd = L.B.max_dd(np.concatenate(chain))
    ann = float(np.prod([1 + yrs[N] for N in READ]) ** (1 / len(READ)) - 1)
    pos = sum(yrs[N] > 0 for N in READ)
    tier = "A" if ann > FROZEN_ANN and dd <= MAX_DD else ("B" if pos >= 4 and dd <= MAX_DD else "C")
    return {"years": {str(k): v for k, v in yrs.items()}, "ann": round(ann, 4), "dd": round(dd, 4), "positive": pos,
            "tier": tier, "chosen": {str(k): v for k, v in chosen.items()}}


def norm(st) -> str:
    return re.sub(r"\s+", "", json.dumps([st.get("asset"), st.get("long_entry"), st.get("long_exit"), st.get("short_entry"),
                                          st.get("short_exit"), st.get("params")], sort_keys=True)).lower()


def load_raw() -> list[dict]:
    out, seen_id, seen_rule = [], set(), {}
    for f in sorted((CAT / "raw").glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                st = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(st, dict) or not st.get("id") or st["id"] in seen_id:
                continue
            seen_id.add(st["id"])
            st["_file"] = f.name
            if st.get("implementable") and st.get("long_entry") or st.get("short_entry"):
                k = norm(st)
                if k in seen_rule:
                    st["duplicate_of"] = seen_rule[k]
                else:
                    seen_rule[k] = st["id"]
            out.append(st)
    return out


def main() -> int:
    CAT.mkdir(parents=True, exist_ok=True)
    allst = load_raw()
    done = {}
    if RES.exists():
        for x in RES.read_text(encoding="utf-8").splitlines():
            if x.strip():
                r = json.loads(x)
                done[r["id"]] = r
    todo = [s for s in allst if s["id"] not in done and not s.get("duplicate_of")
            and (s.get("implementable") and (s.get("long_entry") or s.get("short_entry")))]
    book = Book() if todo else None
    for st in todo:
        try:
            r = {"id": st["id"], "at": now(), **test(book, st)}
        except Exception as exc:  # noqa: BLE001
            r = {"id": st["id"], "at": now(), "tier": "error", "error": f"{type(exc).__name__}: {exc}"[:300]}
        done[st["id"]] = r
        with RES.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r, default=str) + "\n")
        print(f"{st['id']}: {r.get('tier')} {r.get('ann', '')} {r.get('dd', '')}", flush=True)
    write_index(allst, done)
    return 0


def write_index(allst, done) -> None:
    rows = []
    for s in allst:
        r = done.get(s["id"], {})
        if s.get("duplicate_of"):
            status = f"duplicate of {s['duplicate_of']}"
        elif not s.get("implementable"):
            status = "not implementable (data)"
        else:
            status = r.get("tier", "untested")
        rows.append((s, r, status))
    order = {"A": 0, "B": 1, "C": 2, "error": 3}
    rows.sort(key=lambda t: (order.get(t[2], 4), -(t[1].get("ann") or -9)))
    tested = [r for _, r, st in rows if st in ("A", "B", "C")]
    n = {k: sum(1 for _, _, st in rows if st == k) for k in ("A", "B", "C", "error")}
    Lr = ["# Strategy catalogue", "",
          f"Updated {now()}. {len(rows)} strategies indexed, {len(tested)} tested: "
          f"A {n['A']} (beat System 12's frozen book, DD <= 40%), B {n['B']} (positive 4/5 years, DD <= 40%), C {n['C']}, "
          f"errors {n['error']}. Walk-forward 2021-25, 2026 read only. Rules: `SPEC.md`; method: `../catalog12.py`.", "",
          "| verdict | strategy | family | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | per year | DD | source |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s, r, st in rows:
        y = r.get("years", {})
        cells = " | ".join(f"{y[k]:+.0%}" if k in y else "" for k in ("2021", "2022", "2023", "2024", "2025", "2026"))
        ann = f"{r['ann']:+.1%}" if "ann" in r else ""
        dd = f"{r['dd']:.0%}" if "dd" in r else ""
        src = s.get("source_url") or ""
        name = (s.get("name") or s["id"]).replace("|", "/")
        Lr.append(f"| {st} | {name} | {s.get('family', '')} | {cells} | {ann} | {dd} | [{s.get('source_type', 'link')}]({src}) |")
    (CAT / "CATALOG.md").write_text("\n".join(Lr) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
