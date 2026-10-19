"""Plan v2, phase 1: alpha or only beta? (PLAN.md). Runs after PHASE0.md exists.

Benchmarks on the PIT universe, daily, same cost per unit of turnover as the strategy:
  a  BTC buy and hold
  b  equal-weight basket of the year's PIT list, monthly rebalance
  c  b while BTC's previous daily close > its 100-day average, cash otherwise
  d  c with x2 weight on the top 7 coins by 90-day return at each rebalance (the book's momentum factor)
Strategy series: the nested PIT curves and release 48 from phase0_results.json (variants "base" and
"all"), each on both seed sets. Per pair: daily OLS of strategy on benchmark with Newey-West (10 lags)
t-stats; annualised alpha, beta, correlation; Sharpe of each with a 10-day block-bootstrap CI and the
paired bootstrap of the Sharpe difference.

    python research/plan_v2/phase1_alpha.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "phase1_results.json"
HALF_COST = 0.0015
BLOCK, DRAWS = 10, 5000
DAY = 86_400_000_000_000


def daily_closes(symbols: list[str], sealed: bool) -> dict:
    from quantlab_catalog.candles import candles, research
    out = {}
    for s in symbols:
        bars = (candles([s], include_sealed=True).get(s) if sealed else research([s]).get(s)) or []
        if not bars:
            continue
        ns = np.array([np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64") for b in bars])
        day = ns // DAY
        last = np.r_[day[1:] != day[:-1], True]
        out[s] = dict(zip(day[last].tolist(), [b.close for b, k in zip(bars, last) if k]))
    return out


def benchmarks(year: int, coins: list[str], px: dict) -> dict:
    """Daily returns of a-d over `year` (UTC days), costs charged on turnover."""
    d0 = int(np.datetime64(f"{year}-01-01", "D").astype(int))
    d1 = int(np.datetime64(f"{year + 1}-01-01", "D").astype(int))
    days = list(range(d0, d1))
    btc = px["BTCUSDT"]
    bdays = sorted(btc)
    bclose = np.array([btc[d] for d in bdays])
    ma = {d: float(np.mean(bclose[max(0, i - 99): i + 1])) for i, d in enumerate(bdays) if i >= 99}

    def ret(s, d):
        a, b = px.get(s, {}).get(d - 1), px.get(s, {}).get(d)
        return (b / a - 1) if (a and b) else 0.0

    def mom90(s, d):
        a, b = px.get(s, {}).get(d - 91), px.get(s, {}).get(d - 1)
        return (b / a - 1) if (a and b) else -np.inf

    out = {k: [] for k in "abcd"}
    out["a"] = [ret("BTCUSDT", d) for d in days]
    for kind in "bcd":
        w = {}
        for d in days:
            first_of_month = d == d0 or np.datetime64(d, "D").astype("datetime64[M]") != np.datetime64(d - 1, "D").astype("datetime64[M]")
            on = True
            if kind in "cd":
                prev = ma.get(d - 1)
                on = prev is not None and btc.get(d - 1, 0) > prev
            live = [s for s in coins if s in px and d - 1 in px[s]]
            target = w
            if not on:
                target = {}
            elif first_of_month or not w:
                if kind == "d":
                    top = set(sorted(live, key=lambda s: -mom90(s, d))[:7])
                    raw = {s: (2.0 if s in top else 1.0) for s in live}
                else:
                    raw = {s: 1.0 for s in live}
                tot = sum(raw.values()) or 1.0
                target = {s: v / tot for s, v in raw.items()}
            turnover = sum(abs(target.get(s, 0) - w.get(s, 0)) for s in set(target) | set(w))
            r = sum(v * ret(s, d) for s, v in target.items())
            out[kind].append(r - turnover * HALF_COST)
            if target:   # drift
                g = {s: v * (1 + ret(s, d)) for s, v in target.items()}
                tot = sum(g.values()) or 1.0
                w = {s: v / tot for s, v in g.items()}
            else:
                w = {}
    return out


def nw_ols(y: np.ndarray, x: np.ndarray, lags: int = 10) -> dict:
    X = np.c_[np.ones(len(x)), x]
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        G = (X[L:] * e[L:, None]).T @ (X[:-L] * e[:-L, None])
        S += w * (G + G.T)
    XtXi = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(XtXi @ S @ XtXi))
    return {"alpha_ann": round(float(b[0] * 365), 4), "alpha_t": round(float(b[0] / se[0]), 2),
            "beta": round(float(b[1]), 3), "beta_t": round(float(b[1] / se[1]), 2),
            "corr": round(float(np.corrcoef(y, x)[0, 1]), 3)}


def sharpe(x):
    return float(np.mean(x) / (np.std(x, ddof=1) + 1e-12) * np.sqrt(365))


def paired_boot(y: np.ndarray, x: np.ndarray, seed: int = 11) -> dict:
    n = len(y)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / BLOCK))
    idx = (rng.integers(0, n, (DRAWS, nb))[:, :, None] + np.arange(BLOCK)).reshape(DRAWS, -1)[:, :n] % n
    sy, sx = y[idx], x[idx]
    shy = sy.mean(1) / (sy.std(1, ddof=1) + 1e-12) * np.sqrt(365)
    shx = sx.mean(1) / (sx.std(1, ddof=1) + 1e-12) * np.sqrt(365)
    q = lambda a: [round(float(v), 3) for v in np.percentile(a, [5, 50, 95])]  # noqa: E731
    return {"strategy_sharpe": round(sharpe(y), 3), "strategy_p5_p50_p95": q(shy),
            "bench_sharpe": round(sharpe(x), 3), "bench_p5_p50_p95": q(shx),
            "diff_p5_p50_p95": q(shy - shx), "p_diff_le_0": round(float((shy - shx <= 0).mean()), 3)}


def main() -> int:
    from system010_conditioned_rl import pit
    p0 = json.loads((HERE / "phase0_results.json").read_text(encoding="utf-8"))
    lists = {int(y): v for y, v in pit.union_lists(pit.CAP, pit.UNION_YEARS).items()}
    syms = sorted({s for v in lists.values() for s in v})
    px = daily_closes(syms, sealed=False)
    bench = {y: benchmarks(y, lists[y], px) for y in (2022, 2023, 2024, 2025) if y in lists}
    res = {"benchmarks": {y: {k: {"return": round(float(np.prod(1 + np.array(v)) - 1), 4),
                                  "sharpe": round(sharpe(np.array(v)), 3)} for k, v in b.items()} for y, b in bench.items()}}
    for key in ("nested", "nested_confirm", "r48", "r48_confirm"):
        if key not in p0:
            continue
        for var in ("base", "all"):
            yrs = sorted(int(y) for y in p0[key]["per_year"])
            y_s, b_s = [], {k: [] for k in "abcd"}
            for y in yrs:
                dly = p0[key]["per_year"][str(y)][var]["daily"]
                n = len(bench[y]["a"])
                if len(dly) != n:   # align on the last n days (a book whose grid starts late)
                    dly = ([0.0] * (n - len(dly)) + dly) if len(dly) < n else dly[-n:]
                y_s += dly
                for k in "abcd":
                    b_s[k] += bench[y][k]
            ys = np.array(y_s)
            row = {"years": yrs}
            for k in "abcd":
                xb = np.array(b_s[k])
                row[k] = {**(nw_ols(ys, xb) if k in "ab" else {}), **paired_boot(ys, xb)}
            res.setdefault(key, {})[var] = row
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
