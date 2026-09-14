"""THE TRADING POLICY, SHAPED BY WHAT THE MODEL CAN ACTUALLY DO.

Three measured facts decide everything in this file, and none of them is a preference:

1. **The signal lives in weeks, not in days.** `horizons.py` sweeps one day to a quarter on
   the research years alone: mean IC runs +0.05 at 1 day, +0.14 at 7, +0.19 at 14, +0.24 at
   30, +0.27 at 60. A reconstruction of who is out of cash and who is underwater is a
   statement about pressure that takes weeks to show up in a price. v1 asked it for a
   seven-day return because seven was the first number written down.

2. **The level of its forecast is worthless; the ORDER is not.** Over the 2026 window the
   model forecast a rise on 250 days out of 250, averaging +4.84% a week against a realised
   +0.07%. It was trained on 2017-2025, it learned that crypto goes up, and it cannot say
   otherwise. Any policy that reads the model's number as a return will be long everything,
   always - which is exactly what v1's policy did.

3. **Therefore the policy must be CROSS-SECTIONAL.** Rank the universe, buy the top, and
   optionally sell the bottom. A ranking is invariant to the bias in 2: adding five points to
   every forecast changes no ordering at all. This is the single change that converts a
   structurally bullish model into something that can be traded in a falling market.

WHAT IS SELECTED, AND WHERE
Horizon, book shape and width are chosen on the RESEARCH YEARS by walk-forward: for each
year, a model is fitted on everything before it and scores only that year. The candidate must
be positive in EVERY research year - this laboratory's consistency law, learned the hard way
in system 06 - and among those that are, the one with the best WORST year wins. The sealed
window is read once, at the end, with everything already decided.
"""

from __future__ import annotations

import json
import sys

import numpy as np

from quantlab_catalog.paths import REPO_ROOT, indicator_dir
from quantlab_system09 import features as F
from quantlab_system09 import pipeline
from quantlab_system09.train import FOLDS, RESEARCH_END_EXCLUSIVE, _fit

#: Holding periods worth testing. Below a fortnight the 0.30% round trip eats the edge; above
#: a quarter there is not enough independent evidence in eight years to judge it.
HORIZONS = (14, 30, 60, 90)
#: How many names on each side. Three of fourteen is a real concentration; five is most of
#: the market and will track it whatever the model says.
WIDTHS = (3, 4, 5)
#: Long only, or long the top and short the bottom. Shorts are permitted in this repository
#: (operator, 2026-09-08) and the engine models them; what is NOT modelled here is borrow
#: cost, so a long/short book's returns are optimistic by the financing it never pays.
SHAPES = ("long", "long_short")

CAPITAL = 100_000.0
ROUND_TRIP = 0.0030
SEALED_FROM = "2026-01-01"
OUT = REPO_ROOT / "research" / "system09"
MODELS = indicator_dir("system09")


def _walk_forward_scores(ds, years: list[str]) -> np.ndarray:
    """Out-of-sample scores for every research row: each year scored by a model that never
    saw it, and never early-stopped on it either."""
    x = np.hstack([ds.market, ds.ledger])
    score = np.full(len(ds), np.nan)
    for year in years:
        stop = str(int(year) - 1)
        tr = ds.mask(hi=f"{stop}-01-01")
        st = ds.mask(lo=f"{stop}-01-01", hi=f"{year}-01-01")
        va = ds.mask(lo=f"{year}-01-01", hi=f"{int(year) + 1}-01-01")
        if tr.sum() < 2000 or st.sum() < 100 or va.sum() < 100:
            continue
        model, blob, _, _ = _fit(x[tr], ds.y[tr], x[st], ds.y[st])
        score[va] = _apply(model, blob, x[va])
    return score


def _apply(model, blob, x: np.ndarray) -> np.ndarray:
    import torch
    from quantlab_system09.train import DEVICE
    mu, sd = blob["mu"], blob["sd"]
    model.eval()
    with torch.no_grad():
        t = torch.tensor((x - mu) / sd, dtype=torch.float32, device=DEVICE)
        return model(t).cpu().numpy().ravel()


def simulate(ds, score: np.ndarray, prices: dict[str, dict[str, float]], *,
             hold: int, width: int, shape: str, start: str, end: str,
             capital: float = CAPITAL) -> dict:
    """Rebalance every `hold` days into the top `width` names, and hold. That is the whole
    policy: no stop, no filter, no discretion, so that what is measured is the signal.

    Equal dollars per position. A long/short book puts half the capital on each side, so it
    carries the same gross exposure as the long-only one and roughly none of the market.
    """
    days = sorted({d for d in ds.days if start <= d < end})
    if not days:
        return {}
    by_day: dict[str, list[tuple[str, float]]] = {}
    for d, sym, sc in zip(ds.days, ds.symbols, score):
        if d in by_day or (start <= d < end):
            if np.isfinite(sc):
                by_day.setdefault(d, []).append((sym, float(sc)))

    equity, curve, trades = capital, [], []
    book: list[dict] = []
    rebalance_days = days[::hold]
    for i, day in enumerate(days):
        # Mark to market on every day, so the drawdown is the drawdown a holder would live.
        mtm = equity
        for pos in book:
            px = prices.get(pos["symbol"], {}).get(day)
            if px:
                move = (px / pos["entry"] - 1.0) * (1 if pos["side"] == "long" else -1)
                mtm += pos["dollars"] * move
        curve.append({"day": day, "equity": mtm, "open": len(book)})

        if day in rebalance_days or i == len(days) - 1:
            for pos in book:
                px = prices.get(pos["symbol"], {}).get(day) or pos["entry"]
                move = (px / pos["entry"] - 1.0) * (1 if pos["side"] == "long" else -1)
                pnl = pos["dollars"] * (move - ROUND_TRIP)
                equity += pnl
                trades.append({"symbol": pos["symbol"], "side": pos["side"],
                               "entry_day": pos["day"], "exit_day": day,
                               "entry": pos["entry"], "exit": px,
                               "return_pct": move - ROUND_TRIP, "pnl": pnl})
            book = []
            rows = sorted(by_day.get(day, []), key=lambda r: -r[1])
            if len(rows) >= 2 * width and i < len(days) - 1:
                longs = rows[:width]
                shorts = rows[-width:] if shape == "long_short" else []
                per = equity / (width * (2 if shorts else 1))
                for sym, _ in longs:
                    px = prices.get(sym, {}).get(day)
                    if px:
                        book.append({"symbol": sym, "side": "long", "entry": px,
                                     "dollars": per, "day": day})
                for sym, _ in shorts:
                    px = prices.get(sym, {}).get(day)
                    if px:
                        book.append({"symbol": sym, "side": "short", "entry": px,
                                     "dollars": per, "day": day})
    peak, dd = curve[0]["equity"], 0.0
    for p in curve:
        peak = max(peak, p["equity"])
        dd = min(dd, p["equity"] / peak - 1.0)
    wins = [t for t in trades if t["return_pct"] > 0]
    return {"return_pct": equity / capital - 1.0, "final_equity": equity,
            "max_drawdown": dd, "n_trades": len(trades), "wins": len(wins),
            "losses": len(trades) - len(wins),
            "hit_rate": len(wins) / len(trades) if trades else float("nan"),
            "equity": curve, "trades": trades}


def buy_and_hold(traj, y0: str, y1: str) -> float:
    """Equal-weighted return of the whole universe between two dates.

    This row is not decoration. A concentrated crypto basket in 2021 returns several hundred
    per cent because CRYPTO returned several hundred per cent, and a policy that does not beat
    the universe it picks from has demonstrated nothing but exposure. The first version of
    this study printed +1,261% for one year and looked like a triumph; the universe did
    +1,564% in the same year.
    """
    idx = {d: i for i, d in enumerate(traj.days)}
    days = [d for d in traj.days if y0 <= d < y1]
    if not days:
        return float("nan")
    base = {}
    for sym in {s for px in traj.prices for s in px}:
        px = traj.prices[idx[days[0]]].get(sym)
        if px:
            base[sym] = px
    last = traj.prices[idx[days[-1]]]
    rets = [last[s] / base[s] - 1.0 for s in base if last.get(s)]
    return sum(rets) / len(rets) if rets else float("nan")


def _price_map(traj) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for day, px in zip(traj.days, traj.prices):
        for sym, p in px.items():
            out.setdefault(sym, {})[day] = p
    return out


def select(traj, funding, years: list[str]) -> tuple[dict, list[dict]]:
    """Try every candidate on the research years and let the worst year decide."""
    prices = _price_map(traj)
    rows = []
    bh = {y: buy_and_hold(traj, f"{y}-01-01", f"{int(y) + 1}-01-01") for y in years}
    print(f"  {'horizon':>7s} {'width':>6s} {'shape':>11s}   "
          + "".join(f"{y:>9s}" for y in years) + f"{'worst':>9s}{'mean':>9s}")
    print(f"  {'hold it all':>26s}   "
          + "".join(f"{bh[y]:>+8.1%} " for y in years)
          + f"{min(bh.values()):>+8.1%} {sum(bh.values()) / len(bh):>+8.1%}"
          + "   <- doing nothing")
    for h in HORIZONS:
        ds = F.build(traj, funding, horizon=h)
        score = _walk_forward_scores(ds, years)
        for width in WIDTHS:
            for shape in SHAPES:
                per_year = {}
                for y in years:
                    r = simulate(ds, score, prices, hold=h, width=width, shape=shape,
                                 start=f"{y}-01-01", end=f"{int(y) + 1}-01-01")
                    per_year[y] = r.get("return_pct", float("nan"))
                vals = [v for v in per_year.values() if v == v]
                beats = {y: per_year[y] - bh[y] for y in years
                         if per_year[y] == per_year[y] and bh[y] == bh[y]}
                row = {"horizon": h, "width": width, "shape": shape, "per_year": per_year,
                       "worst": min(vals) if vals else float("nan"),
                       "mean": float(np.mean(vals)) if vals else float("nan"),
                       "all_positive": bool(vals) and all(v > 0 for v in vals),
                       "vs_hold": beats,
                       "beats_hold_in": sum(1 for v in beats.values() if v > 0),
                       "beats_hold_every_year": bool(beats) and all(
                           v > 0 for v in beats.values())}
                rows.append(row)
                print(f"  {h:>6d}d {width:>6d} {shape:>11s}   "
                      + "".join(f"{per_year[y]:>+8.1%} " for y in years)
                      + f"{row['worst']:>+8.1%} {row['mean']:>+8.1%}"
                      + f"   beats hold {row['beats_hold_in']}/{len(years)}"
                      + ("  EVERY YEAR" if row["all_positive"] else ""))
    # The bar is not "made money". It is "made money every year AND beat holding every year",
    # because a policy that loses to the universe it selects from has no reason to exist.
    safe = [r for r in rows if r["all_positive"] and r["beats_hold_every_year"]]
    best = max(safe or rows, key=lambda r: (r["worst"], r["mean"]))
    best["qualified"] = bool(safe)
    best["hold_per_year"] = bh
    return best, rows


def main() -> int:
    print("SYSTEM 09 - POLICY: fit the operation to what the model can do")
    print("  selection on research years only, by walk-forward. 2026 is read once, at the "
          "end, with nothing left to choose.\n")
    ctx, traj = pipeline.reconstruct(end="2026-09-14", sealed=True, quiet=True)
    funding = ctx.funding()
    years = [y for y in FOLDS if y < RESEARCH_END_EXCLUSIVE[:4]] or list(FOLDS)

    best, rows = select(traj, funding, years)
    print(f"\n  CHOSEN  {best['horizon']}-day hold, {best['width']} names per side, "
          f"{best['shape']}   worst research year {best['worst']:+.1%}"
          f"   mean {best['mean']:+.1%}")
    if not best.get("qualified"):
        print("\n  NO CANDIDATE QUALIFIED. None of the "
              f"{len(HORIZONS) * len(WIDTHS) * len(SHAPES)} candidates was both positive in "
              "every research year and ahead of simply holding the universe in every "
              "research year. What follows is the best of a failing field, and it is "
              "reported so the failure is on the record rather than hidden by picking a "
              "kinder criterion.")

    # ---- the sealed window, once, with the policy already fixed -------------------
    ds = F.build(traj, funding, horizon=best["horizon"])
    x = np.hstack([ds.market, ds.ledger])
    # EARLY STOPPING IS MODEL SELECTION, so the stopping set is the LAST RESEARCH YEAR and
    # never the sealed one. Fitting on all research and early-stopping on 2026 would let the
    # sealed window choose the epoch - a leak small enough to miss and large enough to matter.
    stop_from = f"{int(RESEARCH_END_EXCLUSIVE[:4]) - 1}-01-01"
    tr = ds.mask(hi=stop_from)
    st = ds.mask(lo=stop_from, hi=RESEARCH_END_EXCLUSIVE)
    va = ds.mask(lo=SEALED_FROM)
    model, blob, _, _ = _fit(x[tr], ds.y[tr], x[st], ds.y[st])
    score = np.full(len(ds), np.nan)
    score[va] = _apply(model, blob, x[va])
    sealed = simulate(ds, score, _price_map(traj), hold=best["horizon"],
                      width=best["width"], shape=best["shape"],
                      start=SEALED_FROM, end="2026-12-31")

    print(f"\n  SEALED 2026 with the chosen policy")
    print(f"    operations            {sealed['n_trades']}")
    print(f"    successful            {sealed['wins']}")
    print(f"    unsuccessful          {sealed['losses']}")
    print(f"    success ratio         {sealed['hit_rate']:.2%}")
    print(f"    return                {sealed['return_pct']:+.2%}")
    print(f"    max drawdown          {sealed['max_drawdown']:.2%}")
    print(f"    final equity          ${sealed['final_equity']:,.0f}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "policy_report.json").write_text(json.dumps({
        "chosen": {k: best[k] for k in ("horizon", "width", "shape", "worst", "mean",
                                        "all_positive", "per_year", "vs_hold",
                                        "beats_hold_in", "beats_hold_every_year")},
        "qualified": best.get("qualified", False),
        "hold_per_year": best.get("hold_per_year", {}),
        "candidates": [{k: r[k] for k in ("horizon", "width", "shape", "worst", "mean",
                                          "all_positive", "per_year", "beats_hold_in")}
                       for r in rows],
        "sealed": {k: sealed[k] for k in ("return_pct", "final_equity", "max_drawdown",
                                          "n_trades", "wins", "losses", "hit_rate")},
        "equity": sealed["equity"], "trades": sealed["trades"],
        "capital": CAPITAL, "round_trip": ROUND_TRIP,
    }, indent=1), encoding="utf-8")
    print(f"\n  written  {OUT / 'policy_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
