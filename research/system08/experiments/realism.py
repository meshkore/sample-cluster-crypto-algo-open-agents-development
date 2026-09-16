"""What the current best book looks like once execution is modelled honestly.

The operator's instruction is that the backtest must respect the market's real constraints:
size against available volume, spreads, and the fact that during a liquidation cascade
orders do not fill where they were asked. Until now this system charged a flat 15 bps per
side regardless of order size, name liquidity or market conditions.

This runs the current best configuration under both models at several book sizes. Book size
is the point: a flat rate is indifferent to it and reality is not, so a result that only
exists at USD 100k is a result that cannot be traded.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat                              # noqa: E402
from quantlab_catalog.paths import universe_file            # noqa: E402
from system008_residual_momentum_ls.system import Config, build          # noqa: E402

BEST = dict(factor="market_ex_self", lookback=21, window=120)
SIZES = (100_000.0, 1_000_000.0, 10_000_000.0, 50_000_000.0)


def main(universe: str = "universe.json") -> int:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    bars = {s: b for s, b in
            cat.research([str(x) for x in meta["symbols"]]).items() if b}
    print(f"{universe}: {len(bars)} names, config {BEST}\n")
    print(f"{'model':<12}{'book USD':>13}{'total':>10}{'maxDD':>9}{'sharpe':>9}"
          f"{'t':>7}{'yrs+':>7}{'cost/yr':>9}")
    for realistic in (False, True):
        for size in SIZES:
            cfg = Config(**BEST, realistic_costs=realistic, initial_equity=size)
            rep = build(bars, cfg, trials=len(SIZES) * 2).report()
            years = [y for y, v in rep["by_year"].items() if abs(v) > 1e-9]
            # Cost as a fraction of the equity it was charged against, per live year.
            days = build(bars, cfg, trials=1).result.days
            per, prev = {}, None
            for d in days:
                base = prev if prev and prev > 0 else d.equity
                per[d.day[:4]] = per.get(d.day[:4], 0.0) + d.cost / base
                prev = d.equity
            live = [v for v in per.values() if v > 0]
            cy = sum(live) / len(live) if live else 0.0
            print(f"{'realistic' if realistic else 'flat':<12}{size:>13,.0f}"
                  f"{rep['total_return']:>10.2f}{rep['max_drawdown']:>9.3f}"
                  f"{rep['sharpe']:>9.3f}{rep['t_stat']:>7.2f}"
                  f"{rep['years_positive']:>4}/{len(years)}{cy:>9.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
