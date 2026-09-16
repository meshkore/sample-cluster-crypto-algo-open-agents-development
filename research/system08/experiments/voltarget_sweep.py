"""Does scaling the book by its own recent volatility remove the bad years?

Momentum's characteristic failure is a crash rather than a bleed, and Barroso and
Santa-Clara (2015) showed that scaling by the strategy's own trailing realised volatility
removes most of it - because momentum's volatility is predictable from its recent past even
when its return is not. Our bad years are 2020 and 2024, and the sealed 2026 is negative,
so this is the overlay aimed squarely at them.

Ours only ever DE-levers: the scale is clamped at 1.0, because leverage here is permitted
but minimal. That gives up part of the published effect and the comparison should say so.
Research years only.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat                              # noqa: E402
from quantlab_catalog.paths import universe_file            # noqa: E402
from system008_residual_momentum_ls.system import Config, build          # noqa: E402

TARGETS = (0.0, 0.60, 0.45, 0.35, 0.25, 0.18)      # annualised; 0.0 = overlay off


def main(universe: str = "universe_wide.json", factor: str = "market_ex_self") -> int:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    bars = {s: b for s, b in
            cat.research([str(x) for x in meta["symbols"]]).items() if b}
    print(f"{universe} / {factor}: {len(bars)} names\n")
    print(f"{'volTgt':>7}{'total':>10}{'maxDD':>9}{'sharpe':>9}{'t':>8}{'yrs+':>7}   years")
    for v in TARGETS:
        run = build(bars, Config(factor=factor, vol_target=v), trials=len(TARGETS))
        rep = run.report()
        yrs = " ".join(f"{str(y)[2:]}:{r:+.2f}" for y, r in sorted(rep["by_year"].items())
                       if str(y) != "2017")
        print(f"{(v or 'off'):>7}{rep['total_return']:>10.3f}{rep['max_drawdown']:>9.3f}"
              f"{rep['sharpe']:>9.3f}{rep['t_stat']:>8.2f}"
              f"{rep['years_positive']:>4}/{rep['years']}   {yrs}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
