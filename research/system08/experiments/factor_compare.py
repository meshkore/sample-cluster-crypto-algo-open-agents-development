"""Does residualising against the cross-section beat residualising against BTC alone?

BTC as the sole factor is the design's declared starting point and its weakness is
structural rather than empirical: it is ONE asset, so whatever the rest of the market does
together lands in the residual and is then ranked as if it were idiosyncratic. A book that
buys high-residual names may partly be buying whatever the non-BTC market just did.

Market-ex-self is the standard correction: the factor is the equal-weight cross-section
with each name removed from its own factor, so no asset explains itself. This measures the
two side by side on research years ONLY. 2026 is unreachable from here.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat                              # noqa: E402
from quantlab_catalog.paths import universe_file            # noqa: E402
from quantlab_system08.system import Config, build          # noqa: E402

FACTORS = ("btc_only", "market_ex_self")


def main(universe: str = "universe_wide.json") -> int:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    declared = [str(s) for s in meta["symbols"]]
    bars = {s: b for s, b in cat.research(declared).items() if b}
    print(f"{universe}: {len(bars)} names with tape\n")

    for factor in FACTORS:
        run = build(bars, Config(factor=factor), trials=len(FACTORS))
        rep = run.report()
        yrs = " ".join(f"{str(y)[2:]}:{v:+.2f}" for y, v in sorted(rep["by_year"].items()))
        print(f"--- {factor}  ({len(run.symbols)} tradable)")
        print(f"    total {rep['total_return']:+.3f}  maxDD {rep['max_drawdown']:.3f}  "
              f"sharpe {rep['sharpe']:.3f}  t {rep['t_stat']:.2f}  "
              f"years+ {rep['years_positive']}/{rep['years']}")
        print(f"    {yrs}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
