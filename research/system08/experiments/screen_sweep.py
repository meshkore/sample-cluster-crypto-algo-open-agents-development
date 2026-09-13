"""Wide factor, narrow book: does trading only the large names beat trading all of them?

The design's third reading front concluded that cross-sectional momentum in crypto lives
in the LARGE names and rejected the small-cap and reversal variants on capacity. Cycle 3
then widened the traded cross-section from fourteen names to thirty-two, which added
eighteen smaller ones, and the sealed year went negative while the backtest improved.

This tests the design's own conclusion instead of contradicting it: the factor keeps all
thirty-two names, because a market estimated from more names is a better estimate and
nobody has to trade an average - while the BOOK trades only the top N by trailing median
USD turnover. Research years only.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat                              # noqa: E402
from quantlab_catalog.paths import universe_file            # noqa: E402
from quantlab_system08.system import Config, build          # noqa: E402

SETTINGS = (0, 24, 18, 14, 10, 8)          # 0 = no screen, trade everything


def main(universe: str = "universe_wide.json", factor: str = "market_ex_self") -> int:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    bars = {s: b for s, b in
            cat.research([str(x) for x in meta["symbols"]]).items() if b}
    print(f"{universe} / {factor}: {len(bars)} names in the factor\n")
    print(f"{'top_n':>6}{'total':>10}{'maxDD':>9}{'sharpe':>9}{'t':>8}{'yrs+':>7}   years")
    for n in SETTINGS:
        run = build(bars, Config(factor=factor, top_n=n), trials=len(SETTINGS))
        rep = run.report()
        yrs = " ".join(f"{str(y)[2:]}:{v:+.2f}" for y, v in sorted(rep["by_year"].items())
                       if str(y) != "2017")
        print(f"{(n or 'all'):>6}{rep['total_return']:>10.3f}{rep['max_drawdown']:>9.3f}"
              f"{rep['sharpe']:>9.3f}{rep['t_stat']:>8.2f}"
              f"{rep['years_positive']:>4}/{rep['years']}   {yrs}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
