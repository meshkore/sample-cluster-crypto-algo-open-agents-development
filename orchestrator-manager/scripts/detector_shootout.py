"""Which mechanism names a bear market while it is still falling?

`detector_diagnosis.py` established three failures of the incumbent detector,
measured on the reference basket 2017-08-17 to 2025-12-31 (the fit era; 2026 is
not on this tape at all):

  * The separation is INVERTED. Forward 20-bar composite return is +1.27% under
    BEAR against +2.64% under BULL and +4.88% under SIDEWAYS. The BEAR label
    does not select falling markets.
  * The lag is fatal. On the three falls it named at all, BEAR arrived 56%, 77%
    and 104% of the way from peak to trough. In 2025 the label landed three
    days AFTER the bottom.
  * The fast falls are invisible. 39.6% in 13 days, 26.5% in 4, 22.1% in 9 --
    never called.

All three have one cause: BEAR requires the slope of a 200-bar average to have
turned. That statistic cannot turn inside a two-month crash, and by the time it
does the crash is over. So the question this script settles is not "is the
detector tuned" but "which mechanism can name a fall while it is still a fall".

Every variant is scored on the detector's own scorecard rather than on strategy
P&L, deliberately: a strategy result mixes the label with the rule, the sizing
and the fills, and cannot say which one moved. What is scored here is only
whether the label orders the future and whether it arrives in time.

    python3 orchestrator-manager/scripts/detector_shootout.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from statistics import median
from typing import Callable

from detector_diagnosis import FOLDS, drawdowns, lag, shares, tape
from quantlab_trading.regime import MarketDetector, MarketRegime, RegimeParameters


@dataclass(frozen=True)
class Variant:
    name: str
    parameters: RegimeParameters
    note: str
    classify: Callable[[MarketDetector, float], MarketRegime] | None = None


def momentum(detector: MarketDetector, share: float) -> MarketRegime:
    """The composite's own return over `slope_period` bars, plus breadth.

    A different family entirely: no trailing average anywhere in the trend
    test, so nothing has to catch up. `trend_period` still governs warmup so
    the variants stay comparable on the same bars.
    """
    period = detector.parameters.slope_period
    if len(detector.index) <= period or detector._averages[-1] is None:
        return MarketRegime.UNKNOWN
    change = detector.index[-1] / detector.index[-1 - period] - 1
    if change > 0.02 and share >= detector.parameters.bull_breadth:
        return MarketRegime.BULL
    if change < -0.02 and share <= detector.parameters.bear_breadth:
        return MarketRegime.BEAR
    return MarketRegime.SIDEWAYS


class Patched(MarketDetector):
    """A detector whose classification step is swapped and nothing else.

    Subclassing rather than copying keeps the composite, the breadth handling,
    the hysteresis and the scorecard identical across every variant, so a
    difference in the table is a difference in the mechanism and cannot be a
    difference in the plumbing.
    """

    def __init__(self, parameters, rule):
        self._rule = rule
        super().__init__(parameters)

    def _classify(self, share: float) -> MarketRegime:
        if self._rule is None:
            return super()._classify(share)
        return self._rule(self, share)


# `require_slope` and `breadth_key` are now real parameters of the shipped
# detector, so every structural variant below is built by CONFIGURING
# `RegimeParameters` rather than by patching `_classify`. Only `momentum`,
# which is a different family and was not adopted, still needs the hook. That
# means this table re-measures the code the router actually runs: if the script
# and the router ever disagree now, they disagree about a parameter value and
# not about a mechanism.
OLD = dict(
    trend_period=200, breadth_key="sma_200", confirmation_bars=20, require_slope=True
)

VARIANTS = (
    Variant(
        "incumbent",
        RegimeParameters(**OLD),
        "200-bar average, its slope, breadth on sma_200, 20-bar confirmation",
    ),
    Variant(
        "no-slope",
        RegimeParameters(**{**OLD, "require_slope": False}),
        "same, minus the slope test",
    ),
    Variant(
        "fast-confirm",
        RegimeParameters(**{**OLD, "confirmation_bars": 5}),
        "incumbent with a 5-bar confirmation instead of 20",
    ),
    Variant(
        "trend-100",
        RegimeParameters(
            trend_period=100,
            breadth_key="sma_100",
            confirmation_bars=10,
            require_slope=True,
        ),
        "a 100-bar trend and breadth, 10-bar confirmation",
    ),
    Variant(
        "trend-50",
        RegimeParameters(
            trend_period=50,
            breadth_key="sma_50",
            confirmation_bars=5,
            require_slope=True,
        ),
        "a 50-bar trend and breadth, 5-bar confirmation",
    ),
    Variant(
        "ADOPTED",
        RegimeParameters(),
        "the shipped defaults: no slope test, 100-bar trend, sma_50 breadth, 5-bar confirm",
    ),
    Variant(
        "momentum",
        RegimeParameters(breadth_key="sma_50", confirmation_bars=5),
        "20-bar composite return past +-2%, breadth on sma_50",
        momentum,
    ),
    # ADOPTED changes four things at once against the incumbent, so on its own
    # it cannot say which of them earned the result. These three hold the slope
    # test dropped and revert exactly one other choice each.
    Variant(
        "ablate-breadth",
        RegimeParameters(trend_period=100, breadth_key="sma_100", confirmation_bars=5),
        "ADOPTED with breadth back on sma_100",
    ),
    Variant(
        "ablate-confirm",
        RegimeParameters(trend_period=100, breadth_key="sma_50", confirmation_bars=20),
        "ADOPTED with the 20-bar confirmation back",
    ),
    Variant(
        "ablate-trend",
        RegimeParameters(trend_period=200, breadth_key="sma_50", confirmation_bars=5),
        "ADOPTED with the 200-bar trend back",
    ),
    # Fairness to the incumbent search. `trend_period` 100-300 and
    # `confirmation_bars` 3-45 were ALREADY searchable, and `slope_period` went
    # down to 5 -- so a very short slope was the closest the loop could get to
    # dropping the test. These two say whether the new levers were needed at
    # all, or whether a wider range would have done.
    Variant(
        "reachable-before",
        RegimeParameters(
            trend_period=100,
            slope_period=5,
            confirmation_bars=5,
            breadth_key="sma_200",
            require_slope=True,
        ),
        "ADOPTED's shape using only levers the loop could already move",
    ),
    Variant(
        "slope-5-fast",
        RegimeParameters(
            trend_period=100,
            slope_period=5,
            breadth_key="sma_50",
            confirmation_bars=5,
            require_slope=True,
        ),
        "as above plus breadth on sma_50, so only the slope test still differs",
    ),
)


def score(variant: Variant, rows) -> dict:
    detector = Patched(variant.parameters, variant.classify)
    for moment, closes, above in rows:
        detector.observe(moment, closes, above)

    separation = detector.separation()
    bear = separation.get("BEAR", {}).get("mean_forward_return")
    bull = separation.get("BULL", {}).get("mean_forward_return")
    sideways = separation.get("SIDEWAYS", {}).get("mean_forward_return")

    falls = drawdowns(detector)
    timings = [lag(detector, episode) for episode in falls]
    called = [t for t in timings if t["called"]]
    episodes = [e for e in detector.episodes() if e.regime is not MarketRegime.UNKNOWN]

    return {
        "detector": detector,
        "bear": bear,
        "bull": bull,
        "sideways": sideways,
        # The one test that matters: does the label order the forward return in
        # the direction the label claims? Anything else is a tuned artifact.
        "ordered": None not in (bear, bull, sideways) and bear < sideways < bull,
        "called": len(called),
        "falls": len(falls),
        "share_of_fall": median([t["share_of_fall"] for t in called])
        if called
        else None,
        "episodes": len(episodes),
        "bear_share": {
            label: shares(detector, *bounds)["BEAR"] for label, bounds in FOLD_BOUNDS
        },
    }


def _bounds():
    from datetime import datetime

    return [
        (
            label,
            (
                datetime.fromisoformat(start + "T00:00:00+00:00"),
                datetime.fromisoformat(end + "T00:00:00+00:00"),
            ),
        )
        for label, start, end in FOLDS
        if label != "2026-fwd"
    ]


FOLD_BOUNDS = _bounds()


def separation_in(detector, start, end, horizon: int = 20) -> dict[str, float]:
    """The scorecard, restricted to one fold.

    Pooling 2017-2026 lets a mechanism win on the two great bull markets and
    stay broken in the fold that falls -- which is precisely the failure
    H-L073O found in the objective. A detector worth adopting has to keep the
    ordering INSIDE the falling fold, where the label is load-bearing.
    """
    buckets: dict[str, list[float]] = {}
    for position, label in enumerate(detector.labels):
        target = position + horizon
        if target >= len(detector.index) or not detector.index[position]:
            continue
        if not (start <= detector.stamps[position] < end):
            continue
        buckets.setdefault(label.value, []).append(
            detector.index[target] / detector.index[position] - 1
        )
    return {k: sum(v) / len(v) for k, v in buckets.items() if v}


def pct(value: float | None, width: int) -> str:
    """A label a variant never emitted has no forward return, and saying so is
    the finding: a mechanism with no SIDEWAYS bucket is a two-state detector."""
    return f"{value:>+{width}.2%}" if value is not None else f"{'none':>{width}}"


def main() -> int:
    rows = list(tape(breadth_period=200))
    fast = list(tape(breadth_period=50))
    medium = list(tape(breadth_period=100))
    by_key = {"sma_200": rows, "sma_100": medium, "sma_50": fast}

    results = {v.name: score(v, by_key[v.parameters.breadth_key]) for v in VARIANTS}

    print("\nDoes the label order the forward 20-bar composite return?")
    print("Wanted: BEAR clearly negative, and BEAR < SIDEWAYS < BULL.\n")
    print(
        f"  {'variant':<15} {'BEAR':>8} {'SIDEWAYS':>9} {'BULL':>8}  {'ordered':>7} "
        f"{'episodes':>8}"
    )
    for variant in VARIANTS:
        r = results[variant.name]
        print(
            f"  {variant.name:<15} {pct(r['bear'], 8)} {pct(r['sideways'], 9)} "
            f"{pct(r['bull'], 8)}  {'YES' if r['ordered'] else 'no':>7} "
            f"{r['episodes']:>8}"
        )

    print("\nDoes BEAR arrive while the market is still falling?")
    print("share_of_fall is the median fraction of peak-to-trough already lost.")
    print("Over 100% means the label landed after the bottom.\n")
    print(f"  {'variant':<15} {'falls named':>12} {'share_of_fall':>14}")
    for variant in VARIANTS:
        r = results[variant.name]
        share = f"{r['share_of_fall']:.0%}" if r["share_of_fall"] is not None else "--"
        print(f"  {variant.name:<15} {r['called']:>7}/{r['falls']:<4} {share:>14}")

    print(
        "\nHow much BEAR does each fold get? A branch that never fires trains nothing.\n"
    )
    header = (
        "  " + f"{'variant':<15}" + "".join(f"{label:>11}" for label, _ in FOLD_BOUNDS)
    )
    print(header)
    for variant in VARIANTS:
        row = results[variant.name]["bear_share"]
        cells = "".join(f"{row[label]:>10.1%} " for label, _ in FOLD_BOUNDS)
        print(f"  {variant.name:<15}{cells}")

    print("\nThe same question one fold at a time: BEAR minus BULL forward return.")
    print("Negative is right -- BEAR should underperform BULL. A positive cell is")
    print("a fold where the label points the wrong way.\n")
    header = (
        "  " + f"{'variant':<15}" + "".join(f"{label:>11}" for label, _ in FOLD_BOUNDS)
    )
    print(header)
    for variant in VARIANTS:
        detector = results[variant.name]["detector"]
        cells = ""
        for label, (start, end) in FOLD_BOUNDS:
            found = separation_in(detector, start, end)
            bear, bull = found.get("BEAR"), found.get("BULL")
            spread = (
                f"{bear - bull:>+9.2%} " if None not in (bear, bull) else f"{'--':>10} "
            )
            cells += spread
        print(f"  {variant.name:<15}{cells}")

    print("\n  " + "-" * 60)
    for variant in VARIANTS:
        print(f"  {variant.name:<15} {variant.note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
