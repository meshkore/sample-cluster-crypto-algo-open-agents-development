"""Would selecting on the past have helped in the future? The only question left.

THE OPERATOR'S OBSERVATION, which is the sharpest thing said about this project: the only
bad year is the one the system was not trained on, and the trained years are not even
spectacular. That is the signature of fitting, and no amount of research-year performance
can answer it - 564 declared trials against one sample means the deflated Sharpe now refuses
everything, correctly.

So this asks the question directly. For each year Y, pick the configuration that looked best
using ONLY the years before Y, then read what that configuration actually did in Y. Repeat
across every year we have. The resulting sequence is what this research process would have
delivered to someone living through it, and it is the honest estimate of what 2026 was
always going to look like.

WHY THIS IS CHEAP, AND WHY THAT IS LEGITIMATE

Every window in this system is causal by construction - loadings, momentum, the liquidity
screen, the seasoning rule and now the cost model all read strictly before the day they act
on. A run truncated at year Y is therefore identical, day for day, to the first part of a
run over the whole tape: nothing downstream can reach back. So each configuration is built
ONCE over the full research era and its per-year returns are read out, rather than rebuilt
per fold. That turns an N x folds problem into N builds.

The saving is only valid because of the causality property, which is asserted by tests
rather than assumed. If a future change lets any window see forward, this file becomes
wrong silently - so it checks the property it depends on rather than trusting it.

WHAT A RESULT LOOKS LIKE

If the edge is real, the configuration chosen on the past should do roughly as well in the
held-out year as it did in the years that chose it. If it is fitting, the held-out years
will be systematically worse than the selection years, and by roughly the margin that
separates our research results from our sealed 2026 reads.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat                              # noqa: E402
from quantlab_catalog.paths import universe_file            # noqa: E402
from system008_residual_momentum_ls.system import Config, build          # noqa: E402

# The candidates. Deliberately the configurations this project actually arrived at, plus
# the region around them, because the question is not "does some configuration work" but
# "would OUR selection process have picked a working one".
CANDIDATES = [
    dict(factor="market_ex_self", window=35, lookback=18, side_fraction=0.25, min_history=365),
    dict(factor="market_ex_self", window=120, lookback=21, min_history=365),
    dict(factor="market_ex_self", window=120, lookback=21, side_fraction=0.25, min_history=365),
    dict(factor="market_ex_self", window=80, lookback=21, side_fraction=0.25, min_history=365),
    dict(factor="market_ex_self", window=60, lookback=21, min_history=365),
    dict(factor="market_ex_self", window=60, lookback=17, min_history=365),
    dict(factor="market_ex_self", window=60, lookback=19, min_history=365),
    dict(factor="market_ex_self", window=60, lookback=23, min_history=365),
    dict(factor="market_ex_self", window=60, lookback=14, min_history=365),
    dict(factor="market_ex_self", window=60, lookback=28, min_history=365),
    dict(factor="market_ex_self", window=60, lookback=28),
    dict(factor="market_ex_self", window=100, lookback=20, side_fraction=0.25, min_history=365),
    dict(factor="btc_only", window=60, lookback=28),
    dict(factor="btc_only", window=120, lookback=21, min_history=365),
    dict(factor="market_ex_self", window=45, lookback=21, side_fraction=0.3, min_history=365),
    dict(factor="market_ex_self", window=150, lookback=21, side_fraction=0.25, min_history=365),
]

MIN_SELECTION_YEARS = 2      # never choose on a single year


def per_year(days) -> dict[str, float]:
    """Each year's return on the equity it started with, so years are comparable."""
    out, prev = defaultdict(float), None
    for d in days:
        base = prev if prev and prev > 0 else d.equity
        out[d.day[:4]] += (d.asset_pnl + d.hedge_pnl + d.funding_pnl - d.cost) / base
        prev = d.equity
    return {y: v for y, v in out.items() if abs(v) > 1e-12}


def score(years: list[float]) -> tuple:
    """How a configuration is judged on the years available so far.

    The same lexicographic order the live loop uses: positive years first, then the worst
    year, then the mean. Using a DIFFERENT rule here would answer a question about a
    selection process nobody runs.
    """
    if not years:
        return (-1, -1.0, -1.0)
    n_pos = sum(1 for v in years if v > 0)
    return (n_pos / len(years), min(years), sum(years) / len(years))


def main(universe: str = "universe_wide.json") -> int:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    bars = {s: b for s, b in
            cat.research([str(x) for x in meta["symbols"]]).items() if b}
    print(f"{universe}: {len(bars)} names, {len(CANDIDATES)} candidates\n")

    table: dict[int, dict[str, float]] = {}
    for i, cfg in enumerate(CANDIDATES):
        run = build(bars, Config(**cfg), trials=len(CANDIDATES))
        table[i] = per_year(run.result.days)
        print(f"  built {i:>2} {str(cfg)[:78]}")

    all_years = sorted({y for v in table.values() for y in v})
    folds = all_years[MIN_SELECTION_YEARS:]
    print(f"\nyears present: {all_years}")
    print(f"walk-forward folds: {folds}\n")
    print(f"{'held-out':<10}{'chosen':>7}{'sel score':>28}{'sel mean':>10}{'HELD-OUT':>10}")

    held, sel_means = [], []
    for y in folds:
        past = [p for p in all_years if p < y]
        best_i, best_key = None, None
        for i, yr in table.items():
            vals = [yr[p] for p in past if p in yr]
            if len(vals) < MIN_SELECTION_YEARS:
                continue
            key = score(vals)
            if best_key is None or key > best_key:
                best_i, best_key = i, key
        if best_i is None:
            continue
        past_vals = [table[best_i][p] for p in past if p in table[best_i]]
        out = table[best_i].get(y)
        if out is None:
            continue
        held.append(out)
        sel_means.append(sum(past_vals) / len(past_vals))
        print(f"{y:<10}{best_i:>7}{str(tuple(round(x,3) for x in best_key)):>28}"
              f"{sel_means[-1]:>10.3f}{out:>10.3f}")

    if held:
        pos = sum(1 for v in held if v > 0)
        print(f"\nHELD-OUT YEARS: {pos}/{len(held)} positive, "
              f"mean {sum(held)/len(held):+.3f}, worst {min(held):+.3f}")
        print(f"SELECTION YEARS mean {sum(sel_means)/len(sel_means):+.3f}")
        print(f"OPTIMISM (selection mean minus held-out mean): "
              f"{sum(sel_means)/len(sel_means) - sum(held)/len(held):+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
