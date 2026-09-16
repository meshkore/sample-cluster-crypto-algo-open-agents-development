"""H2: is the wide book's backtest measuring a cross-section that did not exist yet?

Cycle 3 widened the traded cross-section from fourteen names to thirty-two and every
research year improved while the sealed year reversed sign. Most of the eighteen added
names listed in 2024 or later, so across the research years they contribute a few years
each, while in 2026 they are half the book.

If that is the whole story, requiring a minimum listing history should hurt the backtest
and make it look more like the forward read. If the backtest survives the requirement, the
composition drift is not the explanation and H1 - that 2026 is simply a regime without the
edge - gets the weight instead.

Research years only. This test cannot reach 2026 and does not need to.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat                              # noqa: E402
from quantlab_catalog.paths import universe_file            # noqa: E402
from system008_residual_momentum_ls.system import Config, build          # noqa: E402

SETTINGS = (0, 180, 365, 540, 730)          # days of tape required before a name trades


def main(universe: str = "universe_wide.json", factor: str = "market_ex_self") -> int:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    bars = {s: b for s, b in
            cat.research([str(x) for x in meta["symbols"]]).items() if b}
    print(f"{universe} / {factor}: {len(bars)} names\n")
    print(f"{'minHist':>8}{'total':>10}{'maxDD':>9}{'sharpe':>9}{'t':>8}{'yrs+':>7}   years")
    for h in SETTINGS:
        run = build(bars, Config(factor=factor, min_history=h), trials=len(SETTINGS))
        rep = run.report()
        yrs = " ".join(f"{str(y)[2:]}:{r:+.2f}" for y, r in sorted(rep["by_year"].items())
                       if str(y) != "2017")
        print(f"{(h or 'none'):>8}{rep['total_return']:>10.3f}{rep['max_drawdown']:>9.3f}"
              f"{rep['sharpe']:>9.3f}{rep['t_stat']:>8.2f}"
              f"{rep['years_positive']:>4}/{rep['years']}   {yrs}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
