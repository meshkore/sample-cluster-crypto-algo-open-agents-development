"""Is the signal paying for this book, or is something else?

THE OBSERVATION THAT FORCED THIS

Measuring the information coefficient per year - whether the formation-window residual
momentum score actually predicts the return realised over the following holding period -
produced a table that does not line up with the book's profits:

    2019  IC +0.153   2023  IC -0.003
    2025  IC +0.128   2026  IC +0.030

2023 had the WORST information coefficient of any year, slightly negative, and returned
+61.5%. 2019 and 2025 have the two best ICs and are middling years. 2026's IC is positive
and comparable to 2020, 2021 and 2024, all of which were profitable, yet 2026 loses 26%.

If residual momentum were paying for this book, those columns would move together. They do
not. So either the P&L comes from somewhere else entirely, or the IC is measuring the wrong
thing.

THE TEST

Run the identical machinery - same universe, same residuals, same inverse-residual-volatility
sizing, same gross cap, same hedge, same realistic costs - and replace ONLY the ranking. The
scores are shuffled across names at each rebalance, so the book still holds a long/short
portfolio of the same size and structure, chosen at random.

A placebo is the right instrument because it isolates exactly one thing. Everything that is
not the signal is held identical, so whatever the placebo earns is what the STRUCTURE earns:
the sizing rule, the gross cap, the long/short construction, and any exposure those carry by
accident.

  If the placebo earns roughly nothing, the signal is real and the IC mismatch means the IC
  is the wrong instrument, not that the edge is fake.

  If the placebo earns something close to the real book, then this system's research years
  were never about residual momentum, tuning its parameters was always noise, and the design
  has to be rethought rather than improved.

Several seeds, because one shuffle is an anecdote. Research years only - the placebo does not
need and must not get a sealed read.
"""
from __future__ import annotations

import json
import random
import sys

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat                              # noqa: E402
from quantlab_catalog.paths import universe_file            # noqa: E402
from quantlab_system08 import residual as R                 # noqa: E402
from quantlab_system08 import signal as S                   # noqa: E402
from quantlab_system08.book import daily_funding, run_book  # noqa: E402
from quantlab_system08.system import HEDGE_SYMBOL, Config   # noqa: E402

SEEDS = (1, 2, 3, 4, 5)
CONFIG = dict(factor="market_ex_self", window=35, lookback=18, skip=1, hold=14,
              side_fraction=0.25, min_history=365)


def build_with(bars_by_symbol: dict, config: Config, shuffle_seed: int | None):
    """`system.build`, with one hook: the scores may be shuffled across names.

    This duplicates build() rather than adding a `shuffle` argument to it, deliberately.
    A placebo switch living inside the production path is a switch that can be left on, and
    the one thing worse than not knowing whether the signal works is shipping a book whose
    ranking can be randomised by a stray keyword.
    """
    rets = {s: R.simple_returns(R.daily_closes(b))
            for s, b in bars_by_symbol.items() if b}
    turnover = {s: R.daily_turnover(b) for s, b in bars_by_symbol.items() if b}
    factors = R.market_ex_self(sorted(rets))

    loads = R.residuals(rets, factors=factors, window=config.window)
    eps = R.residual_series(rets, loads, factors=factors)
    hedge_loads = R.residuals(rets, factors=R.BTC_ONLY, window=config.window)

    all_days = sorted({d for v in rets.values() for d in v})
    first_ready = min(min(p) for p in loads.values())
    start = all_days.index(first_ready) if first_ready in all_days else 0
    reb_days = all_days[start::config.hold]

    rng = random.Random(shuffle_seed) if shuffle_seed is not None else None
    targets_on, hedge_on = {}, {}
    for day in reb_days:
        vols = {s: p[day].resid_vol for s, p in loads.items() if day in p}
        if config.min_history:
            seasoned = S.seasoned_names(rets, day, config.min_history)
            vols = {s: v for s, v in vols.items() if s in seasoned}
        betas = {s: p[day].beta for s, p in hedge_loads.items() if day in p}
        if HEDGE_SYMBOL in rets:
            betas[HEDGE_SYMBOL] = 1.0
        if not vols:
            continue

        scores = {}
        for sym in vols:
            sc = S.residual_momentum(eps.get(sym, {}), day,
                                     lookback=config.lookback, skip=config.skip)
            if sc is not None:
                scores[sym] = sc
        if rng is not None and len(scores) > 1:
            # Same names, same score VALUES, reassigned at random. Keeping the values
            # rather than drawing new ones preserves the distribution of the ranking - so
            # the placebo differs from the real book in exactly one respect: which name
            # got which score.
            names = list(scores)
            values = list(scores.values())
            rng.shuffle(values)
            scores = dict(zip(names, values))

        tg = S.rank_and_size(scores, vols, side_fraction=config.side_fraction,
                             gross_cap=config.gross_cap)
        if not tg:
            targets_on[day], hedge_on[day] = [], 0.0
            continue
        targets_on[day] = tg
        hedge_on[day] = S.hedge_weight(tg, betas) * config.hedge_scale

    funding = {}
    for s in list(rets) + [HEDGE_SYMBOL]:
        try:
            rows = cat.funding(s)
        except Exception:
            continue
        if rows:
            funding[s] = daily_funding(rows)

    traded = [d for d in all_days if d >= reb_days[0]] if reb_days else []
    return run_book(traded, rets, targets_on, hedge_on, HEDGE_SYMBOL,
                    funding=funding, initial_equity=config.initial_equity,
                    gross_cap=config.gross_cap, turnover=turnover,
                    realistic_costs=config.realistic_costs)


def summarise(result) -> tuple:
    years, prev = {}, None
    for d in result.days:
        base = prev if prev and prev > 0 else d.equity
        y = d.day[:4]
        years[y] = years.get(y, 0.0) + (d.asset_pnl + d.hedge_pnl + d.funding_pnl
                                        - d.cost) / base
        prev = d.equity
    live = {y: v for y, v in years.items() if abs(v) > 1e-9}
    pos = sum(1 for v in live.values() if v > 0)
    return result.total_return, pos, len(live), (min(live.values()) if live else 0.0), live


def main(universe: str = "universe_wide.json") -> int:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    bars = {s: b for s, b in
            cat.research([str(x) for x in meta["symbols"]]).items() if b}
    cfg = Config(**CONFIG)
    print(f"{universe}: {len(bars)} names, research years only\n")

    total, pos, n, worst, years = summarise(build_with(bars, cfg, None))
    print(f"{'arm':<14}{'total':>10}{'yrs+':>7}{'worst':>9}")
    print(f"{'REAL SIGNAL':<14}{total:>10.3f}{pos:>4}/{n}{worst:>9.3f}")
    print("   " + "  ".join(f"{y[2:]}:{v:+.2f}" for y, v in sorted(years.items())))

    placebo = []
    for seed in SEEDS:
        t, p, nn, w, ys = summarise(build_with(bars, cfg, seed))
        placebo.append(t)
        print(f"{'placebo s' + str(seed):<14}{t:>10.3f}{p:>4}/{nn}{w:>9.3f}")
        print("   " + "  ".join(f"{y[2:]}:{v:+.2f}" for y, v in sorted(ys.items())))

    med = sorted(placebo)[len(placebo) // 2]
    print(f"\nREAL {total:+.3f}   PLACEBO median {med:+.3f} "
          f"(range {min(placebo):+.3f} to {max(placebo):+.3f})")
    print("If those are close, the ranking is not what pays for this book.")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
