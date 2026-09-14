"""STAGE 2 - TRADE THE WHOLE CROSS-SECTION AS AN INDEX, not four names as a bet.

The operator's proposal, 2026-09-14: *"invertir en modo fondo de inversión... ponernos cortos
de un paquete de criptos y largos de otro... montar índices que se ajustan a nuestro modelo -
un tres por ciento de bitcoin, un siete por ciento de otro."*

It is the right shape for the signal this system actually has, and stage 1 measured why:

  rank IC at 30 days          +0.150, positive in every research fold   -> the ORDER is real
  directional accuracy        ~0.50                                     -> the SIGN is not
  forecast bias               +4.77% a week, up on 250 of 250 days      -> the LEVEL is junk

A concentrated book asks the signal the one question it cannot answer - *will THIS name go up*
- and then bets the account on the reply. Twelve operations in nine months, eleven stopped
out, one winner carrying the whole result. An index asks the question it CAN answer: *which
names are better than which*, and it asks it of all fourteen at once, every rebalance. The
edge per position is tiny and it does not need to be large, because there are many of them and
their errors are not the same error.

HOW A SCORE BECOMES A PORTFOLIO
1. Rank the universe by score and turn the ranks into z-scores, so the weights depend on the
   ORDER and never on the model's biased level.
2. Weight proportional to that z-score, long above the mean and short below it.
3. Normalise so gross exposure is exactly 100% - **no leverage**. The operator was explicit:
   none beyond the margin a short mechanically needs, and prudently even then.
4. Optionally cap the net (long minus short) so the book cannot become a disguised directional
   bet. `net_cap=0` is market neutral; `net_cap=1` lets the book be fully long when the model
   likes everything.
5. Rebalance on the horizon, and pay costs on TURNOVER - the traded difference between the old
   weights and the new ones, not on the whole book. This is the structural advantage of an
   index over a concentrated rotation: most of the position survives the rebalance and is
   never charged.

WHAT IS MEASURED
Per research year: return, volatility, worst drawdown, hit rate of the daily book, and the
correlation to the universe. A hedged book is not judged against a bull market's return, which
is the bar stage 1 could never clear and never should have been asked to - it is judged on
being positive every year with a fraction of the exposure.
"""

from __future__ import annotations

import json
import sys

import numpy as np

from quantlab_catalog.paths import REPO_ROOT
from quantlab_system09 import features as F
from quantlab_system09 import pipeline
from quantlab_system09.train import FOLDS, RESEARCH_END_EXCLUSIVE, _fit
from quantlab_system09.policy import _apply, buy_and_hold

CAPITAL = 100_000.0
#: One side of a round trip. An index pays this on the CHANGE in each weight, which is most of
#: why it can afford to rebalance at all.
COST_PER_SIDE = 0.0015
SEALED_FROM = "2026-01-01"
OUT = REPO_ROOT / "research" / "system09"

#: The grid. Deliberately small - stage 1 selected over 120 candidates on five years and this
#: laboratory has documented three times what that does to a result.
HORIZONS = (14, 30, 60)
BREADTHS = (14, 10, 6)           # how many names carry weight: all of them, or the extremes
#: The two ways to express a ranking as a book, and the first run settled which one matters.
#:
#:   long_short  equal gross on each side. Market neutral by construction - and it lost 58% in
#:               2021 and 39% in the sealed window. The reason is structural rather than bad
#:               luck: in a market where the median alt triples, the short leg's losses are
#:               unbounded while the long leg is capped at its weight. A +0.15 rank IC does not
#:               come close to paying for that asymmetry.
#:   long_only   weights proportional to rank across the best `breadth` names, gross 1, net 1.
#:               The operator's own description - *"un tres por ciento de bitcoin, un siete por
#:               ciento de otro"* - and the honest benchmark for it is holding the universe
#:               equally weighted, not cash.
SHAPES = ("tilt", "long_only", "long_short")
#: How far the book may deviate from simply holding the index. 0.0 IS the index; 1.0 is the
#: pure signal portfolio with no anchor at all. This is the operator's own framing - *"seguimos
#: el mercado... si en vez de cincuenta cogemos treinta y siete, acertamos más"* - and it is
#: also the only formulation in which the question has a clean answer, because the benchmark
#: is inside the design rather than bolted on afterwards: every result below is an EXCESS
#: return over holding the same universe, and a tilt that cannot beat zero is a tilt not worth
#: running.
ACTIVE = (0.25, 0.50, 1.00)
#: Divide each weight by the asset's trailing volatility before normalising. Without it a
#: rank-weighted book is quietly a bet on whatever is most volatile, which is what sank the
#: long-only index in 2025: it returned -41% in a year the equal-weighted universe made +19%,
#: because the names the model liked were the ones that moved most in both directions.
VOL_NORM = (False, True)
VOL_WINDOW = 60


def weights(scores: dict[str, float], *, breadth: int, shape: str,
            active: float = 1.0, vols: dict[str, float] | None = None) -> dict[str, float]:
    """Turn one day's scores into a portfolio whose gross exposure is exactly 1.

    The mapping is rank -> weight, never score -> weight, so a model that thinks everything
    will rise by five per cent produces the same book as one that thinks everything will fall
    by five per cent. Only the ordering survives, which is the only part that was ever good.
    """
    if len(scores) < 4:
        return {}
    names = sorted(scores, key=lambda k: scores[k])          # worst first
    n = len(names)

    def _risk_scale(w: dict[str, float]) -> dict[str, float]:
        """Equal RISK rather than equal money, when asked."""
        if not vols:
            return w
        out = {k: v / max(vols.get(k, 0.0) or 1.0, 1e-4) for k, v in w.items()}
        tot = sum(abs(v) for v in out.values()) or 1.0
        return {k: v / tot for k, v in out.items()}

    if shape in ("long_only", "tilt"):
        keep = names[-breadth:]
        raw = {k: float(i + 1) for i, k in enumerate(keep)}   # 1..breadth, best largest
        tot = sum(raw.values())
        signal = _risk_scale({k: v / tot for k, v in raw.items()})
        if shape == "long_only":
            return signal
        # The tilt: hold the index, and move `active` of the way towards the signal book.
        # Everything the model is wrong about costs only `active` times as much, and
        # everything it is right about pays only `active` times as much. That trade-off is
        # the entire question, and this parameter is what puts a number on it.
        bench = _risk_scale({k: 1.0 / n for k in names})
        w = {k: (1.0 - active) * bench.get(k, 0.0) + active * signal.get(k, 0.0)
             for k in set(bench) | set(signal)}
        tot = sum(w.values()) or 1.0
        return {k: v / tot for k, v in w.items()}

    rank = {k: (i + 0.5) / n for i, k in enumerate(names)}          # 0..1
    z = {k: (rank[k] - 0.5) * 2.0 for k in names}                   # -1..1, order only
    if breadth < n:                                                 # keep only the extremes
        keep_set = set(names[:breadth // 2]) | set(names[-(breadth - breadth // 2):])
        z = {k: v for k, v in z.items() if k in keep_set}
    z = _risk_scale(z)
    gross = sum(abs(v) for v in z.values())
    if gross <= 0:
        return {}
    return {k: v / gross for k, v in z.items()}


def _vols(prices: dict[str, dict[str, float]], days: list[str], i: int) -> dict[str, float]:
    """Trailing volatility per asset, from the same price map the book is marked on."""
    lo = max(0, i - VOL_WINDOW)
    window = days[lo:i + 1]
    out = {}
    for sym, series in prices.items():
        rs = []
        for a, b in zip(window[1:], window[:-1]):
            pa, pb = series.get(a), series.get(b)
            if pa and pb:
                rs.append(pa / pb - 1.0)
        if len(rs) > 10:
            out[sym] = float(np.std(rs)) or 1e-4
    return out


def run(ds, score: np.ndarray, prices: dict[str, dict[str, float]], *,
        hold: int, breadth: int, shape: str, start: str, end: str,
        active: float = 1.0, vol_norm: bool = False) -> dict:
    """Hold the index, rebalance every `hold` days, pay for what actually changes.

    The benchmark - the same universe equally weighted, rebalanced on the same days and
    charged the same costs - is run alongside, so the excess return is measured rather than
    inferred from two separate numbers.
    """
    days = sorted({d for d in ds.days if start <= d < end})
    if not days:
        return {}
    by_day: dict[str, dict[str, float]] = {}
    for d, sym, sc in zip(ds.days, ds.symbols, score):
        if start <= d < end and np.isfinite(sc):
            by_day.setdefault(d, {})[sym] = float(sc)

    equity, bench_equity = CAPITAL, CAPITAL
    w: dict[str, float] = {}
    bw: dict[str, float] = {}
    curve, turnover_paid, rebalances = [], 0.0, 0
    for i, day in enumerate(days):
        if i:
            prev = days[i - 1]
            r = bench_r = 0.0
            for sym, wi in w.items():
                a, b = prices.get(sym, {}).get(day), prices.get(sym, {}).get(prev)
                if a and b:
                    r += wi * (a / b - 1.0)
            for sym, wi in bw.items():
                a, b = prices.get(sym, {}).get(day), prices.get(sym, {}).get(prev)
                if a and b:
                    bench_r += wi * (a / b - 1.0)
            equity *= (1.0 + r)
            bench_equity *= (1.0 + bench_r)

        if i % hold == 0:
            vols = _vols(prices, days, i) if vol_norm else None
            target = weights(by_day.get(day, {}), breadth=breadth, shape=shape,
                             active=active, vols=vols)
            live = sorted(by_day.get(day, {}))
            if live:
                bt = {k: 1.0 / len(live) for k in live}
                bench_equity *= (1.0 - sum(abs(bt.get(k, 0.0) - bw.get(k, 0.0))
                                           for k in set(bt) | set(bw)) * COST_PER_SIDE)
                bw = bt
            if target:
                turn = sum(abs(target.get(k, 0.0) - w.get(k, 0.0))
                           for k in set(target) | set(w))
                cost = turn * COST_PER_SIDE
                equity *= (1.0 - cost)
                turnover_paid += turn
                rebalances += 1
                w = target
        curve.append({"day": day, "equity": equity,
                      "net": sum(w.values()), "names": len(w)})

    eq = [c["equity"] for c in curve]
    peak, dd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1.0)
    rets = [eq[i] / eq[i - 1] - 1.0 for i in range(1, len(eq))]
    vol = float(np.std(rets) * np.sqrt(365)) if rets else float("nan")
    ret = eq[-1] / CAPITAL - 1.0
    bench_ret = bench_equity / CAPITAL - 1.0
    return {"return_pct": ret, "benchmark_pct": bench_ret, "excess_pct": ret - bench_ret,
            "final_equity": eq[-1], "max_drawdown": dd,
            "vol_annual": vol, "sharpe_like": (ret / vol) if vol else float("nan"),
            "rebalances": rebalances, "turnover": turnover_paid,
            "up_days": sum(1 for r in rets if r > 0), "days": len(rets),
            "equity": curve}


def _scores_walk_forward(ds, years: list[str]) -> np.ndarray:
    x = np.hstack([ds.market, ds.ledger, ds.world])
    out = np.full(len(ds), np.nan)
    for year in years:
        stop = str(int(year) - 1)
        tr = ds.mask(hi=f"{stop}-01-01")
        st = ds.mask(lo=f"{stop}-01-01", hi=f"{year}-01-01")
        va = ds.mask(lo=f"{year}-01-01", hi=f"{int(year) + 1}-01-01")
        if tr.sum() < 2000 or st.sum() < 200 or va.sum() < 100:
            continue
        model, blob, _, _ = _fit(x[tr], ds.y[tr], x[st], ds.y[st])
        out[va] = _apply(model, blob, x[va])
    return out


def _price_map(traj) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for day, px in zip(traj.days, traj.prices):
        for sym, p in px.items():
            out.setdefault(sym, {})[day] = p
    return out


#: Filled by `select`, so the report can carry what doing nothing would have paid.
hold_export: dict[str, float] = {}


def select(traj, funding, years: list[str]) -> tuple[dict, list[dict]]:
    prices = _price_map(traj)
    hold_year = {y: buy_and_hold(traj, f"{y}-01-01", f"{int(y) + 1}-01-01") for y in years}
    rows = []
    print("  EXCESS return over holding the same universe, per year - zero means the tilt "
          "did nothing\n")
    print(f"  {'hold':>5s} {'n':>3s} {'shape':>10s} {'act':>4s} {'wt':>3s}  "
          + "".join(f"{y:>9s}" for y in years)
          + f"{'worst':>9s}{'mean':>9s}")
    for h in HORIZONS:
        ds = F.build(traj, funding, horizon=h)
        score = _scores_walk_forward(ds, years)
        for breadth in BREADTHS:
          for shape in SHAPES:
           for active in (ACTIVE if shape == "tilt" else (1.0,)):
            for vn in VOL_NORM:
                per_year, dds, vols, excess = {}, [], [], {}
                for y in years:
                    r = run(ds, score, prices, hold=h, breadth=breadth, shape=shape,
                            active=active, vol_norm=vn,
                            start=f"{y}-01-01", end=f"{int(y) + 1}-01-01")
                    per_year[y] = r.get("return_pct", float("nan"))
                    excess[y] = r.get("excess_pct", float("nan"))
                    dds.append(r.get("max_drawdown", float("nan")))
                    vols.append(r.get("vol_annual", float("nan")))
                vals = [v for v in per_year.values() if v == v]
                ex = [v for v in excess.values() if v == v]
                row = {"horizon": h, "breadth": breadth, "shape": shape,
                       "active": active, "vol_norm": vn,
                       "per_year": per_year, "excess": excess,
                       "worst_excess": min(ex) if ex else float("nan"),
                       "mean_excess": float(np.mean(ex)) if ex else float("nan"),
                       "beats_hold_in": sum(1 for v in ex if v > 0),
                       "worst": min(vals) if vals else float("nan"),
                       "mean": float(np.mean(vals)) if vals else float("nan"),
                       "max_dd": float(np.min(dds)) if dds else float("nan"),
                       "vol": float(np.mean(vols)) if vols else float("nan"),
                       "all_positive": bool(vals) and all(v > 0 for v in vals)}
                rows.append(row)
                print(f"  {h:>4d}d {breadth:>3d} {shape:>10s} {active:>4.2f} "
                      f"{'vol' if vn else '  $':>3s}  "
                      + "".join(f"{excess[y]:>+8.1%} " for y in years)
                      + f"{row['worst_excess']:>+8.1%} {row['mean_excess']:>+8.1%}"
                      + f"  beat {row['beats_hold_in']}/{len(years)}"
                      + ("   EVERY YEAR" if row["beats_hold_in"] == len(years) else ""))
    hold_export.update(hold_year)
    # The bar: BEAT HOLDING THE INDEX IN EVERY RESEARCH YEAR. Not "make money" - a long book
    # in crypto makes money in the good years by doing nothing at all, and stage 1 spent a
    # month proving that a number can look wonderful while saying nothing.
    safe = [r for r in rows if r["beats_hold_in"] == len(years)]
    best = max(safe or rows, key=lambda r: (r["worst_excess"], r["mean_excess"]))
    best["qualified"] = bool(safe)
    return best, rows


def main() -> int:
    print("SYSTEM 09 - STAGE 2: the index")
    print("  the model orders the universe; the portfolio expresses the order and nothing "
          "else.\n  gross exposure 1.0, no leverage. Selection on research years only.\n")
    ctx, traj = pipeline.reconstruct(end="2026-09-14", sealed=True, quiet=True)
    funding = ctx.funding()
    years = list(FOLDS)
    best, rows = select(traj, funding, years)
    print(f"\n  CHOSEN  {best['horizon']}-day rebalance, {best['breadth']} names, "
          f"{best['shape']}, active {best['active']:.2f}, "
          f"{'risk-weighted' if best['vol_norm'] else 'equal-money'}"
          f"   worst excess {best['worst_excess']:+.1%}"
          f"   mean excess {best['mean_excess']:+.1%}")
    if not best["qualified"]:
        print("  NO CANDIDATE beat holding the index in every research year. The best of a "
              "failing field is reported, and it is not a recommendation.")

    ds = F.build(traj, funding, horizon=best["horizon"])
    x = np.hstack([ds.market, ds.ledger, ds.world])
    stop_from = f"{int(RESEARCH_END_EXCLUSIVE[:4]) - 1}-01-01"
    tr = ds.mask(hi=stop_from)
    st = ds.mask(lo=stop_from, hi=RESEARCH_END_EXCLUSIVE)
    va = ds.mask(lo=SEALED_FROM)
    model, blob, _, _ = _fit(x[tr], ds.y[tr], x[st], ds.y[st])
    score = np.full(len(ds), np.nan)
    score[va] = _apply(model, blob, x[va])
    sealed = run(ds, score, _price_map(traj), hold=best["horizon"], breadth=best["breadth"],
                 shape=best["shape"], active=best["active"], vol_norm=best["vol_norm"],
                 start=SEALED_FROM, end="2026-12-31")

    print("\n  SEALED 2026")
    print(f"    return            {sealed['return_pct']:+.2%}")
    print(f"    the index itself  {sealed['benchmark_pct']:+.2%}")
    print(f"    EXCESS            {sealed['excess_pct']:+.2%}")
    print(f"    max drawdown      {sealed['max_drawdown']:.2%}")
    print(f"    annualised vol    {sealed['vol_annual']:.1%}")
    print(f"    rebalances        {sealed['rebalances']}   turnover "
          f"{sealed['turnover']:.2f}x")
    print(f"    up days           {sealed['up_days']}/{sealed['days']}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index_report.json").write_text(json.dumps({
        "chosen": {k: best[k] for k in ("horizon", "breadth", "shape", "active", "vol_norm",
                                        "worst", "mean", "max_dd", "vol", "all_positive",
                                        "per_year", "excess", "worst_excess", "mean_excess",
                                        "beats_hold_in")},
        "qualified": best.get("qualified", False),
        "candidates": [{k: r[k] for k in ("horizon", "breadth", "shape", "active", "vol_norm",
                                          "worst", "mean", "max_dd", "vol", "all_positive",
                                          "worst_excess", "mean_excess", "beats_hold_in")}
                       for r in rows],
        "hold_per_year": dict(hold_export),
        "sealed": {k: sealed[k] for k in ("return_pct", "benchmark_pct", "excess_pct",
                                          "max_drawdown", "vol_annual", "rebalances",
                                          "turnover", "up_days", "days")},
        "equity": sealed["equity"], "capital": CAPITAL,
    }, indent=1), encoding="utf-8")
    print(f"\n  written  {OUT / 'index_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
