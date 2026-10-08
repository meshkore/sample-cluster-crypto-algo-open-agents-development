"""S10-6: where do the best trades live, how much of the tape is that, and can it pay?

The operator's question, 2026-09-27, answered before any policy is trained:

1. **The best trades.** 06's zigzag oracle (threshold 0.03) over every research symbol; the
   top quantile of its up-swings by net return after the 0.30% round trip.
2. **The conditions.** For each walk-forward year N, a shallow tree over the frozen
   registry's 44 market columns is fitted on years < N and its densest leaves are taken
   until they cover the target share of those swings (60/70/80/90%). The rules print.
3. **Coverage, out of sample.** In year N: share of bars inside R, share of year N's best
   swings (by the floor fitted on < N) inside R.
4. **Capturable return, out of sample.** A three-slot book, one third of equity per slot,
   enters where R holds and leaves by a CAUSAL exit that reads no model: 06's shipped hard
   stop and trailing stop, and a fixed horizon of 384 bars (four days - the best honest
   horizon in 06's exit study). Costs charged; each year a fresh $100,000 account. This is
   the return R makes reachable without a policy, not the cap.
5. **Version zero** - 06's gates (probability >= enter, slow trend up, breadth, fear) - and
   **everywhere** (enter whenever a slot is free) are scored by the same book, so the learned
   region is measured against the hand-built one and against nothing.
6. **Feasibility.** The 20,000-draw, 21-day-block bootstrap of 365-day years from each
   variant's out-of-sample daily returns: P(year >= +20%), p05, and the chance of a year as
   bad as the worst observed.

Why the exit reads no model. The first run of this tool (2026-09-30) left by 06's band exit
on the live net's probability, and version zero returned +3,313% in 2018. That is not a
result: the live net trained on the first 80% of every symbol's research history, so its
probability on those years is close to the oracle's own label, and an exit that reads it is
an exit with hindsight. Version zero's ENTRY still reads that probability, so version zero is
reported as an in-sample reference only and is excluded from the verdict. The learned region
and the exit read only causal indicators and prices.

No 2026 bar is loaded: bars come from `quantlab_catalog.candles.research()`, and the signal
arrays are joined on those bars' timestamps only.

Run from the repo root:
    PYTHONPATH="trading-system;trading-system/systems;backtester;live-trading" \
        python research/system10/tools/conditions.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
for sub in ("backtester", "trading-system", "trading-system/systems", "live-trading"):
    sys.path.insert(0, str(REPO / sub))

from system010_conditioned_rl import features as registry  # noqa: E402
from system010_conditioned_rl import region as R  # noqa: E402

ENGINE = "v3-exit-010"
YEARS = tuple(range(2018, 2026))
BOOT_YEARS = tuple(range(2019, 2026))   # 2018's region is fitted on 4.5 months of 3 symbols
COVERAGES = (0.6, 0.7, 0.8, 0.9)
QUANTILES = (0.5, 0.3, 0.2)
SLOTS = 3
CAPITAL = 100_000.0
HALF_COST = R.ROUND_TRIP / 2
DD_FLOOR = 0.02
HORIZON = 384           # bars: four days; 06's exit study's best honest horizon


def _q(ret: float, dd: float) -> float:
    return (1.0 if ret >= 0 else -1.0) * ret * ret / max(dd, DD_FLOOR)


# ---------------------------------------------------------------------------- data

def load(engine: str, include_sealed: bool = False) -> dict:
    """Bars, features and channels per symbol. `include_sealed` adds 2026 to today - the
    operator's forward window for system 10 - and is only ever passed by the continuous
    trainer's forward test; swings (the region's teacher) are computed on research bars only.
    """
    from quantlab_catalog.candles import candles, research
    from quantlab_catalog.paths import DATA_ROOT
    from quantlab_live.engine import EnginePackage
    from system006_oracle_net_15m.features import build_matrix, combined_store, research_store
    from system006_oracle_net_15m.moneymodel import _load_features
    from system006_oracle_net_15m.modules.crowd import Crowd

    package = EnginePackage.load(engine)
    symbols = json.loads((REPO / "research/system06/universe.json").read_text())["symbols"]
    bars = candles(symbols, include_sealed=True) if include_sealed else research(symbols)
    signals = REPO / "live-trading/state/engine_cache" / engine / "signals.npz"
    channels = _load_features(str(signals), str(DATA_ROOT), research=bars)
    store = combined_store() if include_sealed else research_store()
    crowd = Crowd(fng_min=1.0)
    fng_ns, fng_val = np.array(crowd._ns, dtype=np.int64), np.array(crowd._val, dtype=float)

    per: dict[str, dict] = {}
    for s in symbols:
        series = bars.get(s) or []
        if len(series) < 1000:
            continue
        X, _ = build_matrix(series, store=store, symbol=s)
        ns = np.array([np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64")
                       for b in series], dtype=np.int64)
        close = np.array([b.close for b in series], dtype=float)
        ch = channels.get(s)
        prob = np.full(len(series), np.nan)
        trend = np.zeros(len(series))
        breadth = np.zeros(len(series))
        if ch is not None:
            pos = np.searchsorted(ch["ns"], ns)
            pos = np.clip(pos, 0, len(ch["ns"]) - 1)
            hit = ch["ns"][pos] == ns
            prob[hit] = ch["prob"][pos[hit]]
            trend[hit] = ch["trend"][pos[hit]]
            breadth[hit] = ch["breadth"][pos[hit]]
        i = np.searchsorted(fng_ns, ns, side="left") - 1
        fng = np.where(i >= 0, fng_val[np.clip(i, 0, None)], np.nan)
        year = ns.astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970
        per[s] = {"X": X.astype(np.float32), "ns": ns, "close": close, "prob": prob,
                  "trend": trend, "breadth": breadth, "fng": fng, "year": year,
                  "swings": R.up_swings(close[year < 2026])}
        print(f"  {s}: {len(series):,} bars, {len(per[s]['swings']):,} oracle up-swings", flush=True)
    return {"per": per, "band": package.band, "risk": package.risk}


# ---------------------------------------------------------------------------- the book

def book_year(per: dict, masks: dict, year: int, band: dict, risk: dict,
              keep: dict | None = None, size: dict | None = None, keep_min_hold: int = 0,
              slots: int = SLOTS, stop: float | None = None, book_stop: float | None = None,
              cooldown: int = 288) -> dict:
    """A fresh three-slot account over one year; enter where `masks` holds.

    Without `keep` the exit is 06's stop + trail + the fixed horizon. With `keep` (per
    symbol, True while the policy wants to stay long) the horizon is replaced by the
    policy's own exit; the stop and trail stay on as the book's safety net.

    Money management (operator, 2026-10-08: "a 50% drawdown is too risky - a model that
    perhaps earns less but does not expose the account"):
      slots      positions the book may hold; each stake is 1/slots of the book
      stop       per-trade stop, replacing 06's 16.3% when given
      book_stop  when the account is this far below its running peak, every position is
                 closed and nothing opens for `cooldown` bars (288 = 3 days); the peak is
                 then reset to the account's value, so the brake measures the new leg
    """
    syms = [s for s in per if (per[s]["year"] == year).any()]
    grid = np.unique(np.concatenate([per[s]["ns"][per[s]["year"] == year] for s in syms]))
    T, S = len(grid), len(syms)
    close = np.full((T, S), np.nan)
    prob = np.full((T, S), np.nan)
    enter = np.zeros((T, S), dtype=bool)
    stay = np.ones((T, S), dtype=bool)
    scale = np.ones((T, S))
    for j, s in enumerate(syms):
        sel = per[s]["year"] == year
        at = np.searchsorted(grid, per[s]["ns"][sel])
        close[at, j] = per[s]["close"][sel]
        prob[at, j] = per[s]["prob"][sel]
        enter[at, j] = masks[s][sel]
        if keep is not None:
            stay[at, j] = keep[s][sel]
        if size is not None:
            scale[at, j] = size[s][sel]
    # Carry the last price across a symbol's missing bars so the book is marked, never
    # traded, on a price nobody printed.
    for j in range(S):
        col = close[:, j]
        ok = np.isfinite(col)
        if ok.any():
            idx = np.where(ok, np.arange(T), 0)
            np.maximum.accumulate(idx, out=idx)
            filled = col[idx]
            filled[: np.argmax(ok)] = np.nan
            close[:, j] = filled
    trail = float(risk.get("trail_stop") or 0)
    stop = float(stop) if stop is not None else float(risk.get("stop_loss") or 0)
    run_peak, frozen_until = CAPITAL, -1

    cash = CAPITAL
    units = np.zeros(S)
    entry_px = np.zeros(S)
    peak_px = np.zeros(S)
    held_for = np.zeros(S, dtype=int)
    held = np.zeros(S, dtype=bool)
    equity = np.empty(T)
    trades: list[float] = []
    for t in range(T):
        px = close[t]
        # exits first, on this bar's close
        for j in np.flatnonzero(held):
            if not np.isfinite(px[j]):
                continue
            held_for[j] += 1
            peak_px[j] = max(peak_px[j], px[j])
            leave = ((stop and px[j] <= entry_px[j] * (1 - stop))
                     or (trail and px[j] <= peak_px[j] * (1 - trail))
                     or held_for[j] >= HORIZON
                     or (keep is not None and not stay[t, j] and held_for[j] >= keep_min_hold))
            if leave:
                cash += units[j] * px[j] * (1 - HALF_COST)
                trades.append(px[j] / entry_px[j] * (1 - HALF_COST) / (1 + HALF_COST) - 1)
                units[j], held[j] = 0.0, False
        if book_stop:
            mark = cash + float(np.nansum(units * np.nan_to_num(px)))
            run_peak = max(run_peak, mark)
            if mark <= run_peak * (1 - book_stop):
                for j in np.flatnonzero(held & np.isfinite(px)):
                    cash += units[j] * px[j] * (1 - HALF_COST)
                    trades.append(px[j] / entry_px[j] * (1 - HALF_COST) / (1 + HALF_COST) - 1)
                    units[j], held[j] = 0.0, False
                frozen_until = t + cooldown
                run_peak = cash + float(np.nansum(units * np.nan_to_num(px)))
        free = slots - int(held.sum()) if t > frozen_until else 0
        if free > 0:
            cand = np.flatnonzero(enter[t] & ~held & np.isfinite(px))
            if len(cand):
                order = cand[:free]  # fixed universe order: priority must not read the in-sample net
                book = cash + float(np.nansum(units * np.nan_to_num(px)))
                for j in order:
                    stake = min(book / slots * scale[t, j], cash)
                    if stake <= 0:
                        break
                    units[j] = stake / (px[j] * (1 + HALF_COST))
                    cash -= stake
                    entry_px[j] = peak_px[j] = px[j]
                    held_for[j], held[j] = 0, True
        equity[t] = cash + float(np.nansum(units * np.nan_to_num(px)))
    peak = np.maximum.accumulate(equity)
    dd = float((1 - equity / peak).max())
    ret = float(equity[-1] / CAPITAL - 1)
    day = grid.astype("datetime64[ns]").astype("datetime64[D]")
    last_of_day = np.r_[day[1:] != day[:-1], True]
    eod = np.r_[CAPITAL, equity[last_of_day]]
    daily = eod[1:] / eod[:-1] - 1
    a = np.array(trades) if trades else np.zeros(0)
    return {"return": round(ret, 4), "max_dd": round(dd, 4), "q": round(_q(ret, dd), 4),
            "trades": len(a), "mean_trade": round(float(a.mean()), 5) if len(a) else None,
            "win_rate": round(float((a > 0).mean()), 4) if len(a) else None,
            "symbols": S, "daily": daily.tolist()}


def bootstrap(daily: list[float], worst_year: float, draws: int = 20_000,
              block: int = 21, days: int = 365, seed: int = 7) -> dict:
    d = np.asarray(daily, dtype=float)
    rng = np.random.default_rng(seed)
    blocks = -(-days // block)
    starts = rng.integers(0, len(d) - block, size=(draws, blocks))
    paths = d[starts[..., None] + np.arange(block)].reshape(draws, -1)[:, :days]
    years = np.prod(1 + paths, axis=1) - 1
    return {"p_year_ge_20": round(float((years >= 0.20).mean()), 4),
            "p05": round(float(np.percentile(years, 5)), 4),
            "median": round(float(np.median(years)), 4),
            "p_as_bad_as_worst": round(float((years <= worst_year).mean()), 4)}


# ---------------------------------------------------------------------------- the study

def study(engine: str, quantile: float) -> dict:
    t0 = time.time()
    print(f"loading bars, indicators and {engine}'s channels (research only)...", flush=True)
    data = load(engine)
    per, band, risk = data["per"], data["band"], data["risk"]
    enter = float(band["enter"])
    breadth_gate = float(risk.get("breadth_gate") or 0)
    fng_min = float(risk.get("fng_min") or 0)

    v0 = {s: (np.nan_to_num(d["prob"]) >= enter) & (d["trend"] > 0)
          & (d["breadth"] >= breadth_gate) & ~(np.nan_to_num(d["fng"], nan=100) < fng_min)
          for s, d in per.items()}
    everywhere = {s: np.isfinite(d["X"]).all(axis=1) for s, d in per.items()}

    variants: dict[str, dict] = {"everywhere": {}, "version zero (06 gates)": {}}
    variants.update({f"R {int(c * 100)}%": {} for c in COVERAGES})
    coverage: dict[str, dict] = {k: {} for k in variants}
    folds: dict[int, dict] = {}

    for N in YEARS:
        # the swings and their floor, from years < N only
        train_nets = np.concatenate([d["swings"][d["year"][d["swings"][:, 0].astype(int)] < N, 2]
                                     for d in per.values() if len(d["swings"])])
        if len(train_nets) < 50:
            continue
        floor = float(np.quantile(train_nets, 1 - quantile))
        Xs, zones, ids, n_best, off = [], [], [], 0, 0
        eval_best: dict[str, np.ndarray] = {}
        for s, d in per.items():
            sw = d["swings"]
            start_year = d["year"][sw[:, 0].astype(int)] if len(sw) else np.zeros(0, int)
            best_train = sw[(start_year < N) & (sw[:, 2] >= floor)]
            eval_best[s] = sw[(start_year == N) & (sw[:, 2] >= floor)]
            tr = d["year"] < N
            if not tr.any():
                continue
            zone = R.entry_zone_mask(len(d["X"]), best_train)
            sid = np.full(len(d["X"]), -1, dtype=np.int64)
            for k, (a, b, _) in enumerate(best_train):
                a = int(a)
                sid[a:min(a + R.ENTRY_ZONE, int(b))] = off + k
            off += len(best_train)
            n_best += len(best_train)
            Xs.append(d["X"][tr]); zones.append(zone[tr]); ids.append(sid[tr])
        X, zone, sid = np.concatenate(Xs), np.concatenate(zones), np.concatenate(ids)
        fold = {"train_years": f"< {N}", "floor_net": round(floor, 4),
                "best_swings_train": int(n_best), "regions": {}}
        n_eval_best = sum(len(v) for v in eval_best.values())
        for c in COVERAGES:
            reg = R.fit(X, zone, sid, n_best, coverage=c, fitted_on=range(2017, N),
                        quantile=quantile, net_floor=floor)
            key = f"R {int(c * 100)}%"
            masks = {s: reg.holds(d["X"]) for s, d in per.items()}
            ev_bars = sum(int(masks[s][per[s]["year"] == N].sum()) for s in per)
            all_bars = sum(int(everywhere[s][per[s]["year"] == N].sum()) for s in per)
            hit = sum(int(R.swings_covered(masks[s], eval_best[s]).sum()) for s in per)
            coverage[key][N] = {"bar_share": round(ev_bars / max(all_bars, 1), 4),
                                "best_swings_inside": round(hit / max(n_eval_best, 1), 4),
                                "best_swings": n_eval_best,
                                "train_bar_share": round(reg.train_bar_share, 4),
                                "train_swing_coverage": round(reg.train_swing_coverage, 4)}
            variants[key][N] = book_year(per, masks, N, band, risk)
            fold["regions"][key] = {"rules": reg.rules(), "leaves": len(reg.leaves)}
        for key, masks in (("everywhere", everywhere), ("version zero (06 gates)", v0)):
            ev_bars = sum(int(masks[s][per[s]["year"] == N].sum()) for s in per)
            all_bars = sum(int(everywhere[s][per[s]["year"] == N].sum()) for s in per)
            hit = sum(int(R.swings_covered(masks[s], eval_best[s]).sum()) for s in per)
            coverage[key][N] = {"bar_share": round(ev_bars / max(all_bars, 1), 4),
                                "best_swings_inside": round(hit / max(n_eval_best, 1), 4),
                                "best_swings": n_eval_best}
            variants[key][N] = book_year(per, masks, N, band, risk)
        folds[N] = fold
        line = "  ".join(f"{k}: {variants[k][N]['return']:+.1%}/{variants[k][N]['max_dd']:.0%}"
                         f" cov {coverage[k][N]['best_swings_inside']:.0%} bars {coverage[k][N]['bar_share']:.0%}"
                         for k in variants)
        print(f"{N} [{time.time() - t0:.0f}s] {line}", flush=True)

    summary = {}
    for k, rows in variants.items():
        yrs = [y for y in BOOT_YEARS if y in rows]
        daily = [v for y in yrs for v in rows[y]["daily"]]
        worst = min(rows[y]["return"] for y in yrs)
        summary[k] = {
            "worst_year": round(worst, 4),
            "worst_q": round(min(rows[y]["q"] for y in yrs), 4),
            "max_dd": round(max(rows[y]["max_dd"] for y in yrs), 4),
            "mean_bar_share": round(float(np.mean([coverage[k][y]["bar_share"] for y in yrs])), 4),
            "mean_best_inside": round(float(np.mean([coverage[k][y]["best_swings_inside"] for y in yrs])), 4),
            "bootstrap": bootstrap(daily, worst),
        }
        for y in rows:
            rows[y].pop("daily")
    return {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "engine": ENGINE, "quantile": quantile, "oracle_threshold": R.ORACLE_THRESHOLD,
            "entry_zone_bars": R.ENTRY_ZONE, "feature_hash": registry.FEATURE_HASH,
            "book": {"slots": SLOTS, "fraction": round(1 / SLOTS, 4), "exit": f"06 stop + trail + {HORIZON}-bar horizon (no model)",
                     "band": band, "stop_loss": risk.get("stop_loss"),
                     "trail_stop": risk.get("trail_stop"), "round_trip": R.ROUND_TRIP},
            "caveat": ("version zero's entry reads the live net's probability, which saw the first "
                       "80% of the research years in training: it is an in-sample reference, not "
                       "a competitor. Every exit is causal and reads no model."),
            "summary": summary, "per_year": variants, "coverage": coverage, "folds": folds,
            "minutes": round((time.time() - t0) / 60, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quantile", type=float, nargs="*", default=[0.2])
    ap.add_argument("--engine", default=ENGINE)
    args = ap.parse_args()
    out_dir = REPO / "research/system10/rnd"
    out_dir.mkdir(parents=True, exist_ok=True)
    for q in args.quantile:
        result = study(args.engine, q)
        path = out_dir / f"conditions_q{int(q * 100)}_{datetime.now(timezone.utc):%Y-%m-%d}.json"
        path.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
        print(f"\nquantile {q}: written {path.relative_to(REPO)}")
        for k, s in result["summary"].items():
            b = s["bootstrap"]
            print(f"  {k:<26} worst yr {s['worst_year']:+.1%}  maxdd {s['max_dd']:.0%}  "
                  f"bars {s['mean_bar_share']:.0%}  best inside {s['mean_best_inside']:.0%}  "
                  f"P(>=20%) {b['p_year_ge_20']:.0%}  p05 {b['p05']:+.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
