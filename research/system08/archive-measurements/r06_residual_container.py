"""R06: the CONTAINER test. Does hedging out Bitcoin leave anything worth owning?

THEORY v2 says an altcoin book carries beta = rho * (sigma_alt/sigma_BTC) units of
Bitcoin, that the exposure is a volatility ratio rather than a regime break, and that a
book which sells that beta and keeps the residual is the right container for whatever
signal we eventually choose.

Kill criterion K2 was registered before any number existed:

    Hedged residual returns must be positive in at least 7 of 9 calendar years.

This script tests it with NO SIGNAL AND NO POSITIONS. The book is the naive equal-weight
altcoin basket -- the dumbest possible content -- hedged with a causal rolling beta. If
the residual of the naive book cannot clear zero most years, no choice of signal rescues
the architecture, because the signal would then have to pay for the container as well as
earn its own return. That is why this runs before the slot `s` is filled and not after.

It is deliberately a test the design can FAIL. There is nothing to tune: the basket is
equal weight, the window is the same 60 days R01 and R05 used, and the universe is fixed
by listing date exactly as in R05. No parameter in this file was chosen after seeing a
result.

WHAT IS MEASURED, PER CALENDAR YEAR 2017-2025

    r_book_t   equal-weight SIMPLE return of the fixed alt universe on day t
    beta_t     Cov_W(r_book, r_B) / Var_W(r_B) over the 60 days ENDING AT t-1
    r_resid_t  r_book_t - beta_t * r_B,t

  and three readings taken from them:

    K2  is the residual positive, and in how many of the nine years
    K4  realised corr(r_resid, r_B) within the year -- if the hedge does not neutralise
        out of sample the book is a directional bet wearing a hedge
    K3  the turnover the hedge implies, from |beta_t - beta_last_rebalance| on the BTC
        leg, charged at the house cost of 30 bps round trip, at three rebalance
        intervals. A container whose hedge costs more than its residual pays is dead
        regardless of signal.

WHY SIMPLE RETURNS AND NOT LOG

  Log returns do not average across assets: the log return of an equal-weight basket is
  not the mean of the constituents' log returns. R05 could use logs because it measured
  each symbol separately. Here a portfolio is formed, so the aggregation must be in
  simple returns or the basket is not the basket.

WHY THE UNHEDGED BASKET IS PRINTED ALONGSIDE

  The comparison that matters is not "is the residual big" but "is the residual better
  behaved than the thing it replaces". If hedging turns losing years positive, the
  container earns its complexity. If it merely shifts the level, it does not.

This measurement builds no strategy, selects nothing, and has no parameters to fit. Under
the operator's code gate (2026-09-10) it is design work -- it is how the design reaches
the bar -- and it cannot be passed by a strategy or flattered by one.

Run from the repo root:
    PYTHONPATH=trading-system python research/system08/tools/r06_residual_container.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

OUT = Path("research/system08/rnd")
FACTOR = "BTCUSDT"
WINDOW = 60                 # trading days, same as R01 and R05 so the three compare
MIN_DAYS = 200
CUTOFF = "2019-01-01"       # fixed universe: names listed before this, as in R05
COST_ROUND_TRIP = 0.0030    # 10 bps commission + 5 bps slippage each way
REBALANCE = (1, 5, 21)      # daily, weekly, monthly -- the hedge's refresh interval
K2_REQUIRED = 7             # of 9 calendar years


def daily_closes(bars) -> dict[str, float]:
    out: dict[str, float] = {}
    for b in bars:
        out[b.timestamp.strftime("%Y-%m-%d")] = float(b.close)
    return out


def simple_returns(series: dict[str, float]) -> dict[str, float]:
    days = sorted(series)
    r = {}
    for prev, day in zip(days, days[1:]):
        p0, p1 = series[prev], series[day]
        if p0 > 0 and p1 > 0:
            r[day] = p1 / p0 - 1.0
    return r


def main() -> int:
    import quantlab_catalog as cat

    symbols = cat.load_universe()
    if FACTOR not in symbols:
        symbols = [FACTOR] + list(symbols)
    print(f"loading {len(symbols)} symbols ...", flush=True)
    research = cat.research(symbols)

    closes: dict[str, dict[str, float]] = {}
    for sym in symbols:
        merged = daily_closes(research.get(sym) or [])
        if len(merged) > MIN_DAYS:
            closes[sym] = merged
    if FACTOR not in closes:
        sys.exit("no BTCUSDT -- the factor is the measurement")

    firsts = {s: min(v) for s, v in closes.items()}
    fixed = sorted(s for s, f in firsts.items() if f < CUTOFF and s != FACTOR)
    dropped = sorted(s for s in closes if s != FACTOR and s not in fixed)
    print(f"  fixed universe (listed before {CUTOFF}): {len(fixed)} names")
    print(f"    {', '.join(fixed)}")
    print(f"  dropped as later listings: {', '.join(dropped) or 'none'}")
    if len(fixed) < 3:
        sys.exit("fewer than three names survive the listing-date cutoff")

    rets = {s: simple_returns(closes[s]) for s in [FACTOR] + fixed}
    btc = rets[FACTOR]

    # ---- the equal-weight basket. A day counts only if BTC and at least three alts
    # have a return on it, so the basket is never one name wearing a portfolio's name.
    days, book, factor_r, widths = [], [], [], []
    for d in sorted(btc):
        vals = [rets[s][d] for s in fixed if d in rets[s]]
        if len(vals) < 3:
            continue
        days.append(d)
        book.append(float(np.mean(vals)))
        factor_r.append(btc[d])
        widths.append(len(vals))

    book_a = np.array(book)
    fac_a = np.array(factor_r)
    print(f"  {len(days)} usable days, {days[0]} .. {days[-1]}, "
          f"basket width {min(widths)}..{max(widths)} names")

    # ---- causal rolling beta. The window ENDS AT t-1: nothing at t decides the hedge
    # held at t. A day before the first full window has no hedge and is not measured.
    beta = np.full(len(days), np.nan)
    for i in range(WINDOW, len(days)):
        wb, wf = book_a[i - WINDOW:i], fac_a[i - WINDOW:i]
        var = float(np.var(wf))
        if var > 0:
            beta[i] = float(np.cov(wb, wf, bias=True)[0, 1]) / var

    resid = book_a - beta * fac_a

    # ---- hedge turnover, per rebalance interval. The BTC leg is resized only on a
    # rebalance day; between them the held hedge is stale, which is the honest version.
    held = {}
    for step in REBALANCE:
        h = np.full(len(days), np.nan)
        cur, cost = np.nan, np.zeros(len(days))
        for i in range(WINDOW, len(days)):
            if np.isnan(beta[i]):
                continue
            if np.isnan(cur) or (i - WINDOW) % step == 0:
                if not np.isnan(cur):
                    cost[i] = abs(beta[i] - cur) * COST_ROUND_TRIP
                cur = beta[i]
            h[i] = cur
        held[step] = (h, cost)

    years = sorted({int(d[:4]) for d in days})
    print("\n" + "=" * 100)
    print("K2 -- THE CONTAINER, PER CALENDAR YEAR.   no signal, no positions, "
          "equal-weight basket")
    print(f"causal {WINDOW}-day beta, hedge refreshed daily; residual = r_book "
          f"- beta*r_BTC")
    print("=" * 100)
    print(f"{'year':>6} {'BTC':>9} {'basket':>9} {'mean beta':>10} {'RESIDUAL':>10} "
          f"{'t-stat':>8} {'corr(e,B)':>10} {'days':>6}")

    rows, positive = {}, 0
    yr_idx = np.array([int(d[:4]) for d in days])
    for y in years:
        m = (yr_idx == y) & ~np.isnan(beta)
        if m.sum() < 100:
            continue
        e = resid[m]
        b, f = book_a[m], fac_a[m]
        comp_r = float(np.prod(1.0 + e) - 1.0)
        comp_b = float(np.prod(1.0 + b) - 1.0)
        comp_f = float(np.prod(1.0 + f) - 1.0)
        sd = float(np.std(e, ddof=1))
        t = float(np.mean(e) / (sd / np.sqrt(len(e)))) if sd > 0 else 0.0
        c = float(np.corrcoef(e, f)[0, 1]) if np.std(f) > 0 else float("nan")
        rows[y] = {
            "btc": comp_f, "basket": comp_b, "residual": comp_r,
            "mean_beta": float(np.nanmean(beta[m])), "t": t, "corr_resid_btc": c,
            "days": int(m.sum()),
        }
        if comp_r > 0:
            positive += 1
        print(f"{y:>6} {comp_f*100:>8.1f}% {comp_b*100:>8.1f}% "
              f"{rows[y]['mean_beta']:>10.3f} {comp_r*100:>9.1f}% {t:>8.2f} "
              f"{c:>10.3f} {m.sum():>6}")

    n = len(rows)
    basket_pos = sum(1 for d in rows.values() if d["basket"] > 0)

    print("\n" + "=" * 100)
    print("THE THREE KILLS THIS MEASUREMENT CAN FIRE")
    print("=" * 100)
    print(f"  K2  residual positive in {positive} of {n} years "
          f"(basket itself: {basket_pos} of {n}).  "
          f"registered bar: {K2_REQUIRED} of 9")
    worst_c = max((abs(d["corr_resid_btc"]) for d in rows.values()), default=float("nan"))
    print(f"  K4  worst |corr(residual, BTC)| in any year: {worst_c:.3f}   "
          "(hedge neutralises only if this stays near zero)")

    mean_resid_bps = float(np.nanmean(resid[~np.isnan(resid)])) * 1e4
    print(f"  K3  mean residual per day: {mean_resid_bps:+.2f} bps, against hedge "
          "rebalancing cost:")
    costs = {}
    for step in REBALANCE:
        _, cost = held[step]
        cbps = float(np.nansum(cost)) / max(1, np.count_nonzero(~np.isnan(beta))) * 1e4
        costs[step] = cbps
        label = {1: "daily", 5: "weekly", 21: "monthly"}[step]
        verdict = "SURVIVES" if mean_resid_bps > cbps else "DEAD ON COSTS"
        print(f"        {label:>8} rebalance  {cbps:>6.2f} bps/day   -> {verdict}")

    print("\n" + "=" * 100)
    if positive >= K2_REQUIRED:
        verdict = (f"K2 HOLDS. The hedged residual of a signal-free equal-weight basket "
                   f"is positive in {positive} of {n} years against a registered bar of "
                   f"{K2_REQUIRED} of 9. The container clears zero before any signal is "
                   f"chosen, which is the only thing this test was ever able to show. "
                   f"It does NOT show the architecture earns the mandate -- that still "
                   f"needs a signal in slot s.")
    else:
        verdict = (f"K2 FIRES. The hedged residual is positive in only {positive} of {n} "
                   f"years, under the registered bar of {K2_REQUIRED} of 9. A signal "
                   f"placed in slot s would have to pay for the container before earning "
                   f"anything of its own. THEORY v2's architecture does not survive this "
                   f"in its present form.")
    print("VERDICT:", verdict)
    print("\nNo signal was used. No position was selected. Nothing here was tuned.")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"r06_residual_container_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    path.write_text(json.dumps({
        "id": "R06", "at": datetime.now(timezone.utc).isoformat(),
        "window_days": WINDOW, "fixed_universe": fixed, "dropped": dropped,
        "listed_before": CUTOFF, "span": [days[0], days[-1]],
        "by_year": rows, "years_positive": positive, "years": n,
        "basket_years_positive": basket_pos,
        "k2_required": K2_REQUIRED,
        "mean_resid_bps_per_day": mean_resid_bps,
        "hedge_cost_bps_per_day": costs,
        "worst_abs_corr_resid_btc": worst_c,
        "verdict": verdict,
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
