"""System 10 on the point-in-time universe (audit 2026-10-15, item 1). Opt-in; nothing else
changes: `search.World()` still loads today's 14 coins, `search.World(universe=N)` loads the
coins eligible for test year N (universe_pit.py, top `CAP` by turnover).

Each test year N gets its own world (its own coins), and inside it the walk-forward is
search.evaluate's: selector fitted on years <= N-2 of those coins, take-bar on N-1, exit
fitted on <= N-1, read on N. Breadth, the momentum rank and the selector's bar see only
that year's coins.

Breadth. 06's engine cache has no channel for coins outside its 14, so here it is rebuilt
from candles exactly as 06 builds it (infer._causal_uptrend over the engine's trend_span,
present from the first full feature row + window - 1, share of present coins in uptrend).
On today's 14 coins it matches the cache (see `check_breadth`).

    python -m system010_conditioned_rl.pit --releases 31 34 43            # PIT re-booking
    python -m system010_conditioned_rl.pit --releases 31 34 43 --baseline # same, today's 14
"""

from __future__ import annotations

import argparse
import gc
import json
import time
from pathlib import Path

import numpy as np

from . import universe_pit as U

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "research/system10/rnd/pit_rebook.json"
CAP = 14          # as many coins as today's list: the A/B isolates survivorship, not width


def load(year: int, include_sealed: bool = False, cap: int | None = CAP,
         symbols: list[str] | None = None, engine: str | None = None) -> dict:
    """search.World's data for the PIT universe of `year`: {"per", "band", "risk"} like
    conditions.load, one coin at a time to keep memory flat."""
    from quantlab_backtester.indicator_store import IndicatorStore
    from quantlab_catalog.candles import candles, research
    from quantlab_catalog.paths import DATA_ROOT
    from quantlab_live.engine import EnginePackage
    from system006_oracle_net_15m.features import build_matrix, finite_rows, research_store
    from system006_oracle_net_15m.infer import _causal_uptrend

    import conditions as C  # research/system10/tools, on the path via search._tools()
    package = EnginePackage.load(engine or C.ENGINE)
    span, window = package.trend_span, int(package.manifest["config"]["window"])
    syms = symbols or U.load(year, cap)
    if "BTCUSDT" not in syms:
        raise ValueError("BTCUSDT must be in the universe: the regime reads its closes")
    # 2026 panels go to a private cache, so no file another process reads is rewritten
    store = (IndicatorStore(DATA_ROOT / "indicators" / "system06" / "combined_pit") if include_sealed
             else research_store())
    per: dict[str, dict] = {}
    for s in syms:
        bars = (candles([s], include_sealed=True).get(s) if include_sealed else None) or research([s]).get(s) or []
        if len(bars) < 1000:
            continue
        X, _ = build_matrix(bars, store=store, symbol=s)
        ns = np.array([np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64") for b in bars],
                      dtype=np.int64)
        close = np.array([b.close for b in bars], dtype=float)
        del bars
        fin = finite_rows(X)
        present = np.zeros(len(ns), dtype=bool)
        if len(fin):
            present[int(fin[0]) + window - 1:] = True
        year_ = ns.astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970
        per[s] = {"X": X.astype(np.float32), "ns": ns, "close": close,
                  "prob": np.full(len(ns), np.nan), "trend": _causal_uptrend(close, span).astype(float),
                  "present": present, "fng": np.full(len(ns), np.nan), "year": year_,
                  "swings": np.zeros((0, 3))}
        print(f"  {s}: {len(ns):,} bars", flush=True)
    breadth_from_candles(per)
    return {"per": per, "band": package.band, "risk": package.risk}


def breadth_from_candles(per: dict) -> None:
    """06's breadth over exactly the coins in `per`: per bar, the share of coins with a channel
    row there whose slow trend is up; 0 on a coin's bars before its own first row."""
    grid = np.unique(np.concatenate([d["ns"][d["present"]] for d in per.values()]))
    up = np.zeros(len(grid))
    cnt = np.zeros(len(grid))
    for d in per.values():
        pos = np.searchsorted(grid, d["ns"][d["present"]])
        np.add.at(cnt, pos, 1)
        np.add.at(up, pos, d["trend"][d["present"]] > 0)
    for d in per.values():
        b = np.zeros(len(d["ns"]))
        pos = np.searchsorted(grid, d["ns"][d["present"]])
        b[d["present"]] = up[pos] / np.maximum(cnt[pos], 1)
        d["breadth"] = b
        d["trend"] = np.where(d["present"], d["trend"], 0.0)


UNION_YEARS = tuple(range(2020, 2026))     # the lists the research bars can use


def union_lists(cap: int | None = CAP, years=UNION_YEARS) -> dict[int, list[str]]:
    return {y: U.load(y, cap) for y in years}


def membership(per: dict, lists: dict[int, list[str]]) -> dict[str, np.ndarray]:
    """Per coin per bar: is the coin in the list of the bar's year? Years before the first
    list use the first (2020's: a coin listed by then, so it traded the years before it -
    training rows only); years after the last use the last."""
    lo, hi = min(lists), max(lists)
    out = {}
    for s, d in per.items():
        yy = np.clip(d["year"], lo, hi)
        m = np.zeros(len(yy), dtype=bool)
        for y, syms in lists.items():
            if s in syms:
                m |= yy == y
        out[s] = m
    return out


def breadth_members(per: dict, member: dict) -> None:
    """breadth_from_candles counted over each bar's MEMBER coins only (that year's list); a
    coin outside the list reads the members' breadth at its bar (0 where there is none)."""
    on = {s: d["present"] & member[s] for s, d in per.items()}
    grid = np.unique(np.concatenate([d["ns"][on[s]] for s, d in per.items()]))
    up, cnt = np.zeros(len(grid)), np.zeros(len(grid))
    for s, d in per.items():
        pos = np.searchsorted(grid, d["ns"][on[s]])
        np.add.at(cnt, pos, 1)
        np.add.at(up, pos, d["trend"][on[s]] > 0)
    for s, d in per.items():
        b = np.zeros(len(d["ns"]))
        if len(grid):
            ns = d["ns"][d["present"]]
            pos = np.clip(np.searchsorted(grid, ns), 0, len(grid) - 1)
            b[d["present"]] = np.where(grid[pos] == ns, up[pos] / np.maximum(cnt[pos], 1), 0.0)
        d["breadth"] = b


def load_union(cap: int | None = CAP, years=UNION_YEARS) -> dict:
    """Review round 2 (R6): ONE research world with every coin of any year's PIT list, plus
    `member` (per coin per bar, in its year's list) and breadth over the members. search.World
    (universe="union") turns `member` into its gate, training rows and book. Never 2026."""
    lists = union_lists(cap, years)
    syms = list(dict.fromkeys(s for y in sorted(lists) for s in lists[y]))
    data = load(min(lists), include_sealed=False, symbols=syms)
    member = membership(data["per"], lists)
    breadth_members(data["per"], member)
    return {**data, "member": member, "lists": lists}


def check_breadth(symbols: list[str]) -> dict:
    """Candle-built breadth vs the engine cache's, on the cache's own coins (research bars)."""
    import conditions as C
    cache = C.load(C.ENGINE)["per"]
    mine = load(2026, symbols=symbols)["per"]
    diff = np.concatenate([np.abs(mine[s]["breadth"] - cache[s]["breadth"]) for s in cache if s in mine])
    return {"bars": int(len(diff)), "equal": round(float((diff < 1e-9).mean()), 6),
            "mean_abs_diff": round(float(diff.mean()), 6), "max_abs_diff": round(float(diff.max()), 4)}


def book(world, cfg: dict, N: int, device: str) -> dict:
    """search.evaluate's body for one year (and forward_reading's for 2026), unchanged."""
    from . import search as S
    g, regime = S.gate(world, cfg)
    share, masks, keep = S.signals(world, cfg, N, g, regime, device)
    st = S.strength(world, cfg, N, g, regime, device) if (cfg.get("size_signal") or cfg.get("scale_in")) else None
    if cfg.get("veto") == "pareto":
        veto, _ = S.pareto_veto(world, cfg, N, g, regime, device)
        if veto:
            masks = {sym: masks[sym] & ~veto[sym] for sym in masks}
    r = world.book(masks, N, cfg["horizon"], S.sizing(world, cfg), keep, S.EXIT_MIN_HOLD,
                   strength=st, **S.mm_kwargs(cfg))
    r.pop("daily")
    r.pop("trade_log", None)
    avail = S.availability(world, g)["per_year"].get(N)
    return {**r, "share": share, "availability": avail}


def summary(years: dict) -> dict:
    from . import search as S
    test = {y: years[y] for y in S.TEST_YEARS if y in years}
    rets = [v["return"] for v in test.values()]
    return {"score": S.law(test, max(v["max_dd"] for v in test.values())),
            "worst_year": round(min(rets), 4),
            "cagr": round(float(np.prod([1 + r for r in rets]) ** (1 / len(rets)) - 1), 4),
            "max_dd": round(max(v["max_dd"] for v in test.values()), 4)}


def rebook(cfgs: dict[str, dict], device: str, universe: str, cap: int | None = CAP) -> dict:
    """Every cfg on 2022-2025 and 2026. universe "pit": one world per year; "today": one world."""
    from . import search as S
    out = {k: {"years": {}} for k in cfgs}
    years = list(S.TEST_YEARS) + [S.FORWARD]
    world, coins = None, {}
    for N in years:
        sealed = N == S.FORWARD
        if universe == "pit" or sealed or world is None:
            world = None
            gc.collect()
            S._SIGNALS.clear()
            t0 = time.time()
            world = S.World(include_sealed=sealed, universe=(N if universe == "pit" else None), cap=cap)
            print(f"[{N}] world: {len(world.per)} coins in {time.time() - t0:.0f}s", flush=True)
        coins[N] = sorted(world.per)
        for k, cfg in cfgs.items():
            r = book(world, cfg, N, device)
            out[k]["years"][N] = r
            print(f"  {k} {N}: {r['return']:+.1%} dd {r['max_dd']:.1%} win {(r['win_rate'] or 0):.1%} "
                  f"{r['trades']} trades", flush=True)
    for k in out:
        out[k].update(summary(out[k]["years"]))
    return {"universe": universe, "cap": cap if universe == "pit" else None, "coins": coins, "runs": out}


def main() -> int:
    import torch

    from . import search as S
    ap = argparse.ArgumentParser(description="Re-book releases on the point-in-time universe")
    ap.add_argument("--releases", nargs="+", default=["31", "champion"],
                    help="release numbers, or 'champion' (search.champion of the ledger)")
    ap.add_argument("--baseline", action="store_true", help="today's 14 coins instead of PIT")
    ap.add_argument("--cap", type=int, default=CAP)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    rel = {r["n"]: r for r in S.releases()}
    cfgs, ids = {}, {}
    for x in a.releases:
        if x == "champion":
            c = S.champion(S.ledger())
            n = next((r["n"] for r in rel.values() if r["id"] == c["id"]), None)
            key = f"release {n} (champion)" if n else f"champion {c['id']}"
            cfgs[key], ids[key] = c["cfg"], c["id"]
        else:
            cfgs[f"release {int(x)}"], ids[f"release {int(x)}"] = rel[int(x)]["cfg"], rel[int(x)]["id"]
    res = rebook(cfgs, a.device, "today" if a.baseline else "pit", a.cap)
    res.update({"at": S._now(), "ids": ids, "seeds": list(S.SEEDS)})
    path = Path(a.out)
    doc = json.loads(path.read_text()) if path.is_file() else {}
    doc[res["universe"]] = res
    path.write_text(json.dumps(doc, indent=1, default=str))
    print(f"-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
