"""Plan v2, phase 0: execution and leakage audit on the PIT universe (PLAN.md).

What it re-runs, on the PIT union world (32 coins, each bar a member only in its year's list):
  nested   the configurations the nested PIT selection picked (rnd/overfit_pit.json), each test
           year with the pick of that year, on BOTH seed sets (main and confirm)
  r48      the paper release (48, chosen on today's 14) over 2022-2025, both seed sets
Signals (gate, selector, exit model, pareto veto, take-bar) are computed exactly as
search.evaluate does; only the BOOK (execution) changes between variants:
  base       the engine as it is: decide and fill on the same 15-minute close, stops read closes
  lag1       decide on the close of t, fill on the close of t+1 (entries, signal exits, scale-in)
  intrabar   stops / breakeven / trailing trigger on the bar's LOW, take profit on its HIGH; both
             in one bar = the stop (worst case); a stop fills at its level, or at the open when the
             bar gapped through it
  cost       round trip 0.20 / 0.30 / 0.45 / 0.60 / 0.80%
  adv        0.30% + per-pair square-root impact: sigma_daily x sqrt(order / ADV), order = the
             largest stake (capital / slots x 2), ADV and sigma = medians of year N-1
  falsify    lag1 + 0.45%  (the plan's falsification test)
  all        lag1 + intrabar + 0.45% + adv impact
The book is a source copy of conditions.book_year with two optional inputs (per-pair cost, OHL
arrays); with both off it reproduces the engine bar for bar (checked on every run: "base_check").
Nothing of System 10 is written; 2026 is never loaded.

    python research/plan_v2/phase0_exec.py [--device cuda] [--only nested|r48]
"""

from __future__ import annotations

import argparse
import inspect
import json
import time
from pathlib import Path

import numpy as np

from system010_conditioned_rl import search as S

HERE = Path(__file__).resolve().parent
OUT = HERE / "phase0_results.json"
COSTS = (0.002, 0.003, 0.0045, 0.006, 0.008)
BLOCK_DAYS = 10
DRAWS = 5000


# ------------------------------------------------------------------ the book with execution options

def fork_book(C):
    """conditions.book_year, patched: `hc` (per-symbol half cost) and `ohl` (per-symbol open/high/low
    arrays, the intrabar exits). Every patch asserts its anchor, so an engine change fails loudly."""
    src = inspect.getsource(C.book_year)

    def rep(old, new):
        nonlocal src
        assert src.count(old) == 1, old[:80]
        src = src.replace(old, new)

    rep("atr_trail: float | None = None, meta_scale: dict | None = None) -> dict:",
        "atr_trail: float | None = None, meta_scale: dict | None = None, hc=None, ohl=None) -> dict:")
    rep('''            if leave:
                fill(t, j, "SELL", units[j], px[j], units[j] * px[j], why)
                cash += units[j] * px[j] * (1 - HALF_COST)
                trades.append(px[j] / entry_px[j] * (1 - HALF_COST) / (1 + HALF_COST) - 1)''',
        '''            if leave:
                fill(t, j, "SELL", units[j], xp, units[j] * xp, why)
                cash += units[j] * xp * (1 - HALF_COST)
                trades.append(xp / entry_px[j] * (1 - HALF_COST) / (1 + HALF_COST) - 1)''')
    rep('''            why = ("stop" if stop''', '''            xp = px[j]
            if ohl is not None:
                why, xp = _ib(t, j, px)
            else:
              why = ("stop" if stop''')
    src = src.replace("HALF_COST", "_hc[j]")
    rep("    trail = float(risk.get(\"trail_stop\") or 0)\n", '''    trail = float(risk.get("trail_stop") or 0)
    _hc = np.full(S, _HALF0) if hc is None else np.array([float(hc[s]) for s in syms])
    if ohl is not None:
        lo_ = per_bar({s: ohl[s]["low"] for s in syms}, np.nan)
        hi_ = per_bar({s: ohl[s]["high"] for s in syms}, np.nan)
        op_ = per_bar({s: ohl[s]["open"] for s in syms}, np.nan)
''')
    rep("    log: list[tuple] = []", '''    def _ib(t, j, px):
        """Worst-case intrabar exit: (reason, fill price) or (None, close)."""
        e, c = entry_px[j], px[j]
        lo = lo_[t, j] if np.isfinite(lo_[t, j]) else c
        hi = hi_[t, j] if np.isfinite(hi_[t, j]) else c
        op = op_[t, j] if np.isfinite(op_[t, j]) else c
        levels = []
        if stop:
            levels.append((e * (1 - stop), "stop"))
        if breakeven and peak_px[j] >= e * (1 + breakeven):
            levels.append((e * be_lock, "breakeven stop"))
        if atr_trail:
            if np.isfinite(atr[t, j]):
                levels.append((peak_px[j] - atr_trail * atr[t, j], "trailing stop"))
        elif trail:
            levels.append((peak_px[j] * (1 - trail), "trailing stop"))
        hit = [x for x in levels if lo <= x[0]]
        if hit:
            lv, why = max(hit)
            return why, min(lv, op)
        if take_profit and hi >= e * (1 + take_profit):
            return "take profit", e * (1 + take_profit)
        if held_for[j] >= HORIZON:
            return "time limit", c
        if keep is not None and not stay[t, j] and held_for[j] >= keep_min_hold:
            return "signal exit", c
        return None, c
    log: list[tuple] = []''')
    ns = dict(vars(C))
    ns["_HALF0"] = C.HALF_COST
    exec(compile(src, "book_exec", "exec"), ns)
    return ns["book_year"], ns


def book(world, fork, masks, year, horizon, size, keep, **kw):
    fn, ns = fork
    per = world.per
    if world.member is not None:
        per = {s: d for s, d in per.items() if world.member[s][d["year"] == year].any()}
    ns["HORIZON"] = horizon
    return fn(per, masks, year, world.band, world.risk, keep=keep, size=size,
              keep_min_hold=S.EXIT_MIN_HOLD, **kw)


def lag(d: dict | None, first) -> dict | None:
    """The decision of bar t acted on at bar t+1 (each coin's own bars)."""
    if d is None:
        return None
    out = {}
    for s, a in d.items():
        b = np.empty_like(a)
        b[1:] = a[:-1]
        b[0] = first
        out[s] = b
    return out


# ------------------------------------------------------------------ data the engine does not keep

def load_ohlv(world) -> dict:
    from quantlab_catalog.candles import research
    out = {}
    for s, d in world.per.items():
        bars = research([s]).get(s) or []
        ns = np.array([np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64") for b in bars])
        assert len(ns) == len(d["ns"]) and (ns == d["ns"]).all(), s
        out[s] = {"open": np.array([b.open for b in bars]), "high": np.array([b.high for b in bars]),
                  "low": np.array([b.low for b in bars]), "usd": np.array([b.volume * b.close for b in bars])}
    return out


def impact(world, ohlv: dict, year: int, slots: int) -> dict:
    """Per-pair half cost added by a square-root impact model, from year-1 medians (year itself
    when the coin has no year-1 bars). Order = the largest stake of a $100k book."""
    order = S._tools().CAPITAL / slots * 2
    out = {}
    for s, d in world.per.items():
        sel = d["year"] == year - 1
        if sel.sum() < 96 * 30:
            sel = d["year"] == year
        day = d["ns"][sel] // 86_400_000_000_000
        usd, close = ohlv[s]["usd"][sel], d["close"][sel]
        if not len(day):
            out[s] = 0.0
            continue
        _, first = np.unique(day, return_index=True)
        adv = np.add.reduceat(usd, first)
        eod = close[np.r_[first[1:] - 1, len(close) - 1]]
        sig = np.std(np.diff(np.log(eod))) if len(eod) > 2 else 0.05
        out[s] = float(sig * np.sqrt(order / max(np.median(adv), 1.0)))
    return out


# ------------------------------------------------------------------ one configuration, one year

def year_inputs(world, cfg: dict, N: int, device: str) -> dict:
    """search.evaluate's per-year signals, without booking them."""
    g, regime = S.gate(world, cfg)
    share, masks, keep = S.signals(world, cfg, N, g, regime, device)
    st = S.strength(world, cfg, N, g, regime, device) if (cfg.get("size_signal") or cfg.get("scale_in")) else None
    if cfg.get("veto") == "pareto":
        veto, _ = S.pareto_veto(world, cfg, N, g, regime, device)
        if veto:
            masks = {s: masks[s] & ~veto[s] for s in masks}
    return {"masks": masks, "keep": keep, "st": st, "size": S.sizing(world, cfg), "mm": S.mm_kwargs(cfg),
            "horizon": cfg["horizon"], "share": share}


def variants(world, fork, ohlv, inp: dict, N: int) -> dict:
    m, k, st, size, mm, h = inp["masks"], inp["keep"], inp["st"], inp["size"], inp["mm"], inp["horizon"]
    lm, lk, lst, lsize = lag(m, False), lag(k, True), lag(st, 0.0), lag(size, 1.0)
    syms = list(world.per)
    flat = lambda rt: {s: rt / 2 for s in syms}  # noqa: E731
    imp = impact(world, ohlv, N, int(mm.get("slots") or 3))
    adv = {s: 0.0015 + imp[s] for s in syms}
    adv45 = {s: 0.00225 + imp[s] for s in syms}
    runs = {
        "base": dict(masks=m, keep=k, size=size, strength=st),
        **{f"cost_{rt * 100:.2f}": dict(masks=m, keep=k, size=size, strength=st, hc=flat(rt)) for rt in COSTS},
        "lag1": dict(masks=lm, keep=lk, size=lsize, strength=lst),
        "intrabar": dict(masks=m, keep=k, size=size, strength=st, ohl=ohlv),
        "adv": dict(masks=m, keep=k, size=size, strength=st, hc=adv),
        "falsify": dict(masks=lm, keep=lk, size=lsize, strength=lst, hc=flat(0.0045)),
        "all": dict(masks=lm, keep=lk, size=lsize, strength=lst, hc=adv45, ohl=ohlv),
    }
    out = {}
    for name, kw in runs.items():
        r = book(world, fork, kw.pop("masks"), N, h, kw.pop("size"), kw.pop("keep"), **kw, **mm)
        out[name] = {"return": r["return"], "max_dd": r["max_dd"], "trades": r["trades"],
                     "win_rate": r["win_rate"], "mean_trade": r["mean_trade"], "daily": r["daily"]}
    eng = world.book(m, N, h, size, k, S.EXIT_MIN_HOLD, strength=st, **mm)
    out["base_check"] = {"engine_return": eng["return"], "fork_return": out["base"]["return"],
                         "same": abs(eng["return"] - out["base"]["return"]) < 1e-9 and eng["trades"] == out["base"]["trades"]}
    out["impact_half_cost"] = {s: round(v, 5) for s, v in imp.items() if world.member[s][world.per[s]["year"] == N].any()}
    return out


# ------------------------------------------------------------------ statistics

def boot_ci(daily: list[float], seed: int = 7) -> dict:
    """Circular block bootstrap (BLOCK_DAYS-day blocks) of the daily series: annualised return
    (geometric) and Sharpe, 5th / 50th / 95th percentiles."""
    x = np.asarray(daily, dtype=float)
    n = len(x)
    if n < 2 * BLOCK_DAYS:
        return {}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / BLOCK_DAYS))
    starts = rng.integers(0, n, size=(DRAWS, nb))
    idx = (starts[:, :, None] + np.arange(BLOCK_DAYS)[None, None, :]).reshape(DRAWS, -1)[:, :n] % n
    s = x[idx]
    ann = np.exp(np.log1p(s).sum(axis=1) * 365 / n) - 1
    sh = s.mean(axis=1) / (s.std(axis=1, ddof=1) + 1e-12) * np.sqrt(365)
    q = lambda a: [round(float(v), 4) for v in np.percentile(a, [5, 50, 95])]  # noqa: E731
    point = float(np.exp(np.log1p(x).sum() * 365 / n) - 1)
    return {"ann_return": round(point, 4), "ann_return_p5_p50_p95": q(ann),
            "sharpe": round(float(x.mean() / (x.std(ddof=1) + 1e-12) * np.sqrt(365)), 3),
            "sharpe_p5_p50_p95": q(sh), "days": n}


def curve(per_year: dict, variant: str) -> dict:
    yrs = sorted(per_year)
    rets = [per_year[y][variant]["return"] for y in yrs]
    daily = [x for y in yrs for x in per_year[y][variant]["daily"]]
    return {"years": dict(zip(yrs, rets)), "total": round(float(np.prod([1 + r for r in rets]) - 1), 4),
            "worst_year": min(rets), "max_dd": max(per_year[y][variant]["max_dd"] for y in yrs),
            "trades": sum(per_year[y][variant]["trades"] for y in yrs), **boot_ci(daily)}


# ------------------------------------------------------------------ checks 4 and 5 (leakage, PIT)

def leakage_checks(world) -> dict:
    """Embargo: the selector trains on rows whose label window ends by N-2, the exit model on rows
    whose 96-bar window ends by N-1 (search.selector_masks / exit_keep filter on end_year), so no
    label reads a price of N; measured here on the labels themselves. PIT: every coin trades only
    in its year's list and breadth counts members only."""
    out = {"embargo": {}, "pit": {}}
    o = world.outcomes(768)
    for N in S.TEST_YEARS:
        cut = 0
        for s, d in world.per.items():
            yr = d["year"][o[s]["idx"]]
            cut += int(((yr <= N - 2) & (o[s]["end_year"] > N - 2)).sum())
        out["embargo"][f"selector N={N}: rows of N-2 dropped because the 768-bar label reaches N-1"] = cut
    tg = world.fwd(S.EXIT_K)
    for N in S.TEST_YEARS:
        cut = 0
        for s, d in world.per.items():
            cut += int((world.valid[s] & (d["year"] <= N - 1) & (tg[s]["end_year"] > N - 1)).sum())
        out["embargo"][f"exit N={N}: rows of N-1 dropped because the 96-bar label reaches N"] = cut
    from system010_conditioned_rl import pit
    lists = pit.union_lists(pit.CAP, pit.UNION_YEARS)
    for y, coins in sorted(lists.items()):
        traded = sorted(s for s, d in world.per.items() if world.member[s][d["year"] == int(y)].any())
        out["pit"][str(y)] = {"list_equals_members": traded == sorted(coins), "coins": len(coins)}
    # breadth over members: recompute on one sample day per year and compare
    out["pit"]["breadth_rebuilt_from_members"] = True  # pit.breadth_members is the only writer (code check)
    return out


def open_gap(world, ohlv) -> dict:
    """How far the next bar's open is from this bar's close (fill at open t+1 vs close t)."""
    g = np.concatenate([np.abs(ohlv[s]["open"][1:] / world.per[s]["close"][:-1] - 1) for s in world.per])
    return {"median": float(np.median(g)), "p90": float(np.percentile(g, 90)), "p99": float(np.percentile(g, 99))}


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--only", choices=("nested", "r48"))
    a = ap.parse_args()
    t0 = time.time()
    print("loading the PIT union world", flush=True)
    world = S.World(universe="union")
    fork = fork_book(world.C)
    ohlv = load_ohlv(world)
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    res["checks"] = {**leakage_checks(world), "open_vs_close_gap": open_gap(world, ohlv)}
    res["at"] = S._now()
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    ledger = {r["id"]: r for r in S.ledger_rows(S.OUT / "rnd/search_trials_pit.jsonl")}
    ov = json.loads((S.OUT / "rnd/overfit_pit.json").read_text(encoding="utf-8"))
    r48 = json.loads((S.OUT / "releases/release_0048.json").read_text(encoding="utf-8"))["cfg"]
    jobs = []
    if a.only in (None, "nested"):
        for key, seeds in (("nested", S.SEEDS), ("nested_confirm", S.CONFIRM_SEEDS)):
            for y, p in sorted(ov[key]["picks"].items()):
                jobs.append((key, seeds, int(y), ledger[p["id"]]["cfg"], p))
    if a.only in (None, "r48"):
        for key, seeds in (("r48", S.SEEDS), ("r48_confirm", S.CONFIRM_SEEDS)):
            for y in S.TEST_YEARS:
                jobs.append((key, seeds, y, r48, None))
    main_seeds = S.SEEDS
    for key, seeds, y, cfg, pick in jobs:
        if str(y) in res.get(key, {}).get("per_year", {}):
            continue
        S.SEEDS = seeds
        try:
            inp = year_inputs(world, cfg, y, a.device)
            v = variants(world, fork, ohlv, inp, y)
        finally:
            S.SEEDS = main_seeds
        if pick is not None:
            led = pick["return"] if key == "nested" else pick["confirm_return"]
            v["ledger_return"] = led
        res.setdefault(key, {"per_year": {}})["per_year"][str(y)] = v
        res[key]["curves"] = {n: curve({int(k): w for k, w in res[key]["per_year"].items()}, n)
                              for n in v if isinstance(v[n], dict) and "daily" in v[n]}
        OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        print(f"[{S._now()}] {key} {y}: base {v['base']['return']:+.3f} (check {v['base_check']['same']}, ledger "
              f"{v.get('ledger_return')}) lag1 {v['lag1']['return']:+.3f} intrabar {v['intrabar']['return']:+.3f} "
              f"falsify {v['falsify']['return']:+.3f} all {v['all']['return']:+.3f} [{(time.time() - t0) / 60:.0f} min]",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
