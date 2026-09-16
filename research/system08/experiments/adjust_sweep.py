"""Does trading partway toward the target beat trading all the way? Research years only.

The decomposition said cost took 4.7-5.9% of equity in every research year and in 2026,
larger in the weak years than everything the signal earned. `adjust` is the one lever that
attacks that directly, and this measures it on research data ONLY - 2026 is not read here
and nothing in this file can reach it, because `cat.research()` cannot return a sealed bar.

Reported per setting: total return, drawdown, Sharpe, the cost the book paid as a fraction
of equity per year, and how many of the nine years were positive. The last column is the
one that matters most to this laboratory's standing criterion.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat                              # noqa: E402
from quantlab_catalog.paths import universe_file            # noqa: E402
from system008_residual_momentum_ls.system import Config, build          # noqa: E402

SETTINGS = (1.0, 0.75, 0.5, 0.35, 0.25, 0.15)


def cost_per_year(days) -> float:
    """Mean annual cost as a fraction of the equity it was charged against."""
    per = defaultdict(float)
    prev = None
    for d in days:
        base = prev if prev and prev > 0 else d.equity
        per[d.day[:4]] += d.cost / base
        prev = d.equity
    live = [v for k, v in per.items() if v > 0]
    return sum(live) / len(live) if live else 0.0


def main(universe: str = "universe_wide.json") -> int:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    declared = [str(s) for s in meta["symbols"]]
    bars = {s: b for s, b in cat.research(declared).items() if b}
    print(f"{universe}: {len(bars)} names with tape\n")
    print(f"{'adjust':>7}{'total':>10}{'maxDD':>9}{'sharpe':>9}{'t':>8}"
          f"{'cost/yr':>9}{'yrs+':>6}")
    for a in SETTINGS:
        run = build(bars, Config(adjust=a), trials=len(SETTINGS))
        rep = run.report()
        print(f"{a:>7.2f}{rep['total_return']:>10.3f}{rep['max_drawdown']:>9.3f}"
              f"{rep['sharpe']:>9.3f}{rep['t_stat']:>8.2f}"
              f"{cost_per_year(run.result.days):>9.3f}"
              f"{rep['years_positive']:>4}/{rep['years']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
