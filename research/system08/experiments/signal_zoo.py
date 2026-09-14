"""Is there a ranking whose raw material does not die when momentum's does?

THE POSITION THIS STARTS FROM

System 08's machinery is sound and measured: the hedge, the inverse-residual-volatility
sizing, realistic execution with a capacity ceiling, a walk-forward harness whose optimism
is NEGATIVE, and a placebo that refutes chance. Exactly one component failed in the sealed
year, and it is the ranking. `quartile_spread.py` showed the top-minus-bottom holding-period
return was +2.3% to +5.9% in every research year and -1.79% in 2026, and
`adaptive_exposure.py` then showed the book cannot be taught to see that coming from the
inside, because eight years of research data contain no persistent inversion to learn from.

So the question is not how to protect residual momentum. It is whether a DIFFERENT ranking,
carried by the same machinery, has a different failure mode - and the honest way to ask that
is to compare the candidates' raw material directly rather than their profits.

WHAT IS MEASURED, AND WHY IT IS THE SPREAD RATHER THAN THE P&L

Every candidate is run through the identical pipeline: same universe, same residuals, same
seasoning, same quartiles, same holding period. Only the score changes. For each one this
reports, per year, the mean holding-period return of the top quarter minus the bottom - the
number the book actually lives on, before sizing, hedging or costs can flatter or obscure it.

Then the number that decides everything: the CORRELATION, cycle by cycle, between each
candidate's spread and residual momentum's. A candidate that pays well but moves in lockstep
with momentum is the same bet wearing a different name, and it will invert on the same day.
A candidate whose spread is uncorrelated is a genuinely separate source of return, and a book
holding both is exposed to momentum's failure in proportion to how much of it it holds.

THE CANDIDATES, and the reason each one is not just another parameter

  momentum     the incumbent, for reference.
  carry        the cross-section of funding rates. Economically the opposite trade: funding
               is paid BY crowded longs, so ranking on it shorts crowding rather than
               chasing it. Note this is not the funding-as-income idea already killed - that
               measured the cash the existing book collected and found it was noise. This
               ranks names BY it, which is a different object entirely.
  lowvol       long the low-residual-volatility quarter. The oldest surviving cross-sectional
               anomaly outside crypto and the one least related to trend.
  reversal     the negative of the most recent short residual move. Mechanically the
               opposite sign to momentum at a shorter horizon, so if momentum inverted
               because the market started mean-reverting, this is what was paying instead.
  slow         residual momentum over a much longer formation window. Included as a CONTROL:
               it should correlate highly with momentum, and if it does not, the correlation
               statistic is not measuring what this script claims.

SELECTION USES RESEARCH YEARS ONLY. Screening candidates on the sealed year would be
choosing a signal because it survived 2026, which is the sealed year used as feedback and is
the one thing this project has refused for nine months.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat                              # noqa: E402
from quantlab_catalog.paths import universe_file            # noqa: E402
from quantlab_system08 import residual as R                 # noqa: E402
from quantlab_system08 import signal as S                   # noqa: E402

WINDOW, LOOKBACK, SKIP, HOLD = 35, 18, 1, 14
SIDE = 0.25
MIN_HISTORY = 365
SLOW_LOOKBACK = 60      # the control's formation window
REVERSAL_DAYS = 5       # the short horizon reversal looks back over
CARRY_DAYS = 14         # trailing window the funding rate is averaged over


def compounded(series, days, i, n):
    if i - n < 0 or i > len(days):
        return None
    acc = 1.0
    for d in days[i - n:i]:
        v = series.get(d)
        if v is None:
            return None
        acc *= (1.0 + v)
    return acc - 1.0


def daily_funding_rate(rows: list[dict]) -> dict[str, float]:
    """Funding settlements collapsed to a per-day total, keyed by date.

    Summed rather than averaged: three settlements a day at one basis point is three basis
    points of carry, and a name that settles more often genuinely pays more.
    """
    import datetime as _dt
    out: dict[str, float] = defaultdict(float)
    for r in rows:
        ms = r.get("t_ms")
        rate = r.get("rate")
        if ms is None or rate is None:
            continue
        day = _dt.datetime.utcfromtimestamp(ms / 1000.0).strftime("%Y-%m-%d")
        out[day] += float(rate)
    return dict(out)


def trailing_mean(series: dict[str, float], day: str, n: int) -> float | None:
    """Mean of the last n observations STRICTLY BEFORE `day`. None if short."""
    have = sorted(d for d in series if d < day)
    if len(have) < n:
        return None
    return float(np.mean([series[d] for d in have[-n:]]))


def main(universe: str = "universe_wide.json") -> int:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    syms = [str(s) for s in meta["symbols"]]
    bars = {s: b for s, b in cat.research(syms).items() if b}
    rets = {s: R.simple_returns(R.daily_closes(b)) for s, b in bars.items()}
    rets = {s: v for s, v in rets.items() if v}

    factors = R.market_ex_self(sorted(rets))
    loads = R.residuals(rets, factors=factors, window=WINDOW)
    eps = R.residual_series(rets, loads, factors=factors)

    funding = {}
    for s in rets:
        try:
            rows = cat.funding(s)
        except Exception:
            continue
        if rows:
            funding[s] = daily_funding_rate(rows)

    all_days = sorted({d for v in rets.values() for d in v})
    idx = {d: i for i, d in enumerate(all_days)}
    first = min(min(p) for p in loads.values())
    reb_days = all_days[idx.get(first, 0)::HOLD]

    def score_momentum(sym, day, vol):
        return S.residual_momentum(eps.get(sym, {}), day, lookback=LOOKBACK, skip=SKIP)

    def score_slow(sym, day, vol):
        return S.residual_momentum(eps.get(sym, {}), day, lookback=SLOW_LOOKBACK, skip=SKIP)

    def score_reversal(sym, day, vol):
        v = S.residual_momentum(eps.get(sym, {}), day, lookback=REVERSAL_DAYS, skip=SKIP)
        return None if v is None else -v

    def score_carry(sym, day, vol):
        f = funding.get(sym)
        if not f:
            return None
        m = trailing_mean(f, day, CARRY_DAYS)
        # Long the names whose longs are NOT paying to be there: negate the rate.
        return None if m is None else -m

    def score_lowvol(sym, day, vol):
        return None if not vol or vol <= 0 else -vol

    scorers = {"momentum": score_momentum, "carry": score_carry,
               "lowvol": score_lowvol, "reversal": score_reversal, "slow": score_slow}

    # cycle -> {signal: spread}; one pass over the rebalances, all signals together, so
    # every candidate sees exactly the same cross-section on exactly the same days.
    per_cycle: dict[str, dict[str, float]] = defaultdict(dict)
    for day in reb_days:
        i = idx[day]
        if i + 2 * HOLD >= len(all_days):
            continue
        seasoned = S.seasoned_names(rets, day, MIN_HISTORY)
        vols = {s: loads[s][day].resid_vol for s in seasoned
                if s in loads and day in loads[s]}
        if len(vols) < 8:
            continue

        def fwd(sym):
            return compounded(rets.get(sym, {}), all_days, i + HOLD, HOLD)

        fwds = {s: fwd(s) for s in vols}
        for name, fn in scorers.items():
            sc = {}
            for s in vols:
                v = fn(s, day, vols[s])
                if v is not None and np.isfinite(v):
                    sc[s] = v
            if len(sc) < 8:
                continue
            ranked = sorted(sc, key=lambda s: sc[s], reverse=True)
            k = max(2, int(len(ranked) * SIDE))
            top = [fwds[s] for s in ranked[:k] if fwds.get(s) is not None]
            bot = [fwds[s] for s in ranked[-k:] if fwds.get(s) is not None]
            if len(top) < 2 or len(bot) < 2:
                continue
            per_cycle[day][name] = float(np.mean(top)) - float(np.mean(bot))

    years = sorted({d[:4] for d in per_cycle})
    print(f"{universe}: {len(bars)} names, {len(per_cycle)} cycles, research only")
    print("\nMEAN HOLDING-PERIOD SPREAD PER YEAR (top quarter minus bottom quarter)\n")
    print(f"{'signal':<11}" + "".join(f"{y[2:]:>8}" for y in years)
          + f"{'mean':>9}{'yrs+':>7}")
    table: dict[str, dict[str, float]] = {}
    for name in scorers:
        row = {}
        for y in years:
            vals = [c[name] for d, c in per_cycle.items() if d[:4] == y and name in c]
            if vals:
                row[y] = float(np.mean(vals))
        table[name] = row
        vals = list(row.values())
        print(f"{name:<11}" + "".join(f"{row.get(y, float('nan')) * 100:>8.2f}"
                                      for y in years)
              + f"{np.mean(vals) * 100:>9.2f}"
              + f"{sum(1 for v in vals if v > 0):>4}/{len(vals)}")
    print("(percent per 14-day cycle)")

    print("\nCORRELATION OF CYCLE SPREAD WITH MOMENTUM'S - the number that decides.")
    print("Near 1.0 means the same bet renamed; near 0 means a separate source of return.")
    print("'slow' is the control: it MUST come out high or this statistic is broken.\n")
    print(f"{'signal':<11}{'corr vs momentum':>19}{'cycles':>9}")
    for name in scorers:
        pairs = [(c["momentum"], c[name]) for c in per_cycle.values()
                 if "momentum" in c and name in c]
        if len(pairs) < 30:
            print(f"{name:<11}{'too few':>19}{len(pairs):>9}")
            continue
        a = np.array([p[0] for p in pairs]); b = np.array([p[1] for p in pairs])
        c = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else float("nan")
        print(f"{name:<11}{c:>19.3f}{len(pairs):>9}")

    print("\nA candidate is worth building on only if it clears BOTH bars: a positive mean")
    print("spread in most years, AND a low correlation with momentum. High mean and high")
    print("correlation is the trade we already own; low correlation and no return is noise.")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
