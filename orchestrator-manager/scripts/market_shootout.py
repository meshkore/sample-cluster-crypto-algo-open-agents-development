"""What is "the market", and does a wider one detect its own turns better?

The major-trend detector reads a composite of SIX assets. The operator's point
is that the trend it is trying to name is a property of the whole market -- a
bull run ends at peak total capitalisation and a bear ends at the trough -- and
six survivors are not that. This measures whether widening the basket actually
improves the call, or only makes it sound better.

WHAT WE CAN AND CANNOT BUILD, said plainly. True market capitalisation is
price times circulating supply, and this laboratory holds no supply data at
all: the archive is Binance OHLCV and nothing else. So "total market value" is
not computable here today, and every index below is a PROXY for it. The closest
proxy available is turnover weighting -- bigger coins trade more -- and it is
measured here against the alternatives rather than assumed to be best.
Acquiring supply data is a task, not a footnote; it is written up in the
initiative this script belongs to.

FOUR CANDIDATE MARKETS:

    basket-6-equal    the incumbent: six survivors, equal weight
    all-equal         every asset listed on the bar, equal weight
    all-turnover      every asset, weighted by trailing dollar volume
    all-sqrt          every asset, weighted by the square root of turnover

Equal weight and turnover weight disagree about what a market IS, and the
disagreement is the whole question. Equal weight is a statement about the
median coin; turnover weight is a statement about where the money is, and
collapses toward "BTC plus noise" as concentration rises. The square root
variant is the standard damping between the two.

HOW THEY ARE COMPARED, and why it is not obvious. Each detector runs on its own
composite, so scoring each against its OWN forward return would let a variant
win by being easy to predict rather than by being right. Every variant is
therefore scored against ONE benchmark: the forward return of the broad
equal-weighted index, which is the closest thing this laboratory has to "what
the market did". A detector's job is to call the market's turns, not its own.

    python3 orchestrator-manager/scripts/market_shootout.py [--assets N]
"""

from __future__ import annotations

import csv
import math
import sys
from collections import deque
from datetime import datetime
from statistics import median

from detector_diagnosis import CANDLES, FOLDS, trailing_average
from quantlab_trading.regime import (
    REFERENCE_BASKET,
    MarketDetector,
    MarketRegime,
    RegimeParameters,
)

TURNOVER_WINDOW = 20


def load_all(
    limit: int | None = None,
) -> dict[str, dict[datetime, tuple[float, float]]]:
    """Every asset's (close, dollar volume) by timestamp.

    Dollar volume is close times base volume. It is not the exchange's own
    quote-volume field -- that is not in the processed CSV -- but on a daily bar
    the difference is second-order and the number is used only as a WEIGHT, so a
    few percent of error moves nothing.
    """
    out: dict[str, dict[datetime, tuple[float, float]]] = {}
    folders = sorted(p for p in CANDLES.iterdir() if p.is_dir())
    if limit:
        folders = folders[:limit]
    for folder in folders:
        files = (
            sorted((folder / "1d").glob("*.csv")) if (folder / "1d").is_dir() else []
        )
        if not files:
            continue
        series: dict[datetime, tuple[float, float]] = {}
        with files[0].open() as handle:
            for row in csv.DictReader(handle):
                try:
                    close = float(row["close"])
                    volume = float(row["volume"] or 0.0)
                except (TypeError, ValueError):
                    continue
                if close > 0:
                    series[datetime.fromisoformat(row["timestamp"])] = (
                        close,
                        close * volume,
                    )
        if len(series) > TURNOVER_WINDOW:
            out[folder.name] = series
    return out


def turnover_averages(
    market: dict[str, dict[datetime, tuple[float, float]]],
) -> dict[str, dict[datetime, float]]:
    """Trailing dollar volume per asset -- the size proxy, and the liquidity
    gate's own statistic, so the weighting agrees with what the book can buy."""
    out: dict[str, dict[datetime, float]] = {}
    for symbol, series in market.items():
        stamps = sorted(series)
        window: deque[float] = deque(maxlen=TURNOVER_WINDOW)
        values: dict[datetime, float] = {}
        for stamp in stamps:
            window.append(series[stamp][1])
            values[stamp] = sum(window) / len(window)
        out[symbol] = values
    return out


def composite(
    market: dict[str, dict[datetime, tuple[float, float]]],
    stamps: list[datetime],
    weighting: str,
    turnover: dict[str, dict[datetime, float]],
    universe: tuple[str, ...] | None = None,
) -> list[float]:
    """A chained index over whatever was listed on each bar.

    Chaining the WEIGHTED MEAN RETURN rather than averaging levels is what makes
    this survive listings and delistings: an asset joins the average on the
    first bar where it has both a close and a previous close, and its absent
    history neither dilutes nor rebases the index. Averaging prices or summing
    values would jump the day an asset appears -- a level change with no market
    event behind it, which on a 386-asset universe happens constantly.

    That is also why this cannot be called a capitalisation index even under
    turnover weighting: a real one would be the SUM of values and would move
    when a coin is created. This moves only when prices move.
    """
    names = universe if universe is not None else tuple(market)
    previous: dict[str, float] = {}
    level = 100.0
    out: list[float] = []
    for stamp in stamps:
        pairs = []
        for symbol in names:
            bar = market.get(symbol, {}).get(stamp)
            if bar is None:
                continue
            close = bar[0]
            before = previous.get(symbol)
            if before:
                if weighting == "equal":
                    weight = 1.0
                else:
                    size = turnover.get(symbol, {}).get(stamp, 0.0)
                    weight = math.sqrt(size) if weighting == "sqrt" else size
                if weight > 0:
                    pairs.append((math.log(close / before), weight))
            previous[symbol] = close
        if pairs:
            total = sum(w for _, w in pairs)
            level *= math.exp(sum(r * w for r, w in pairs) / total)
        out.append(level)
    return out


def breadth(
    market: dict[str, dict[datetime, tuple[float, float]]],
    stamps: list[datetime],
    period: int,
    universe: tuple[str, ...] | None = None,
) -> list[float]:
    """Share of the listed universe trading above its own trailing average.

    Computed over every asset rather than six, which is the point: breadth is
    the one statistic that is MEANINGLESS on a small basket. Six names can only
    ever report 0, 1/6, 2/6 ... and the detector's thresholds sit at 0.35 and
    0.50, so on the incumbent basket the difference between a bear market and a
    bull one is one asset changing its mind.
    """
    names = universe if universe is not None else tuple(market)
    averages: dict[str, dict[datetime, float | None]] = {}
    for symbol in names:
        series = market.get(symbol)
        if not series:
            continue
        order = sorted(series)
        closes = [series[s][0] for s in order]
        averages[symbol] = dict(zip(order, trailing_average(closes, period)))
    out = []
    for stamp in stamps:
        above = total = 0
        for symbol in names:
            series = market.get(symbol, {})
            bar = series.get(stamp)
            average = averages.get(symbol, {}).get(stamp)
            if bar is None or average is None:
                continue
            total += 1
            above += bar[0] > average
        out.append(above / total if total else 0.0)
    return out


class Precomputed(MarketDetector):
    """A detector fed a composite that was built outside it.

    `MarketDetector` builds its own equal-weighted index from the reference
    basket, which is exactly the thing under test here. Feeding the level and
    the breadth directly keeps the CLASSIFICATION -- the trend test, the
    thresholds, the hysteresis, the scorecard -- identical across variants, so a
    difference in the table is a difference in what "the market" means and not
    in how a trend is called.
    """

    def push(self, stamp: datetime, level: float, share: float) -> MarketRegime:
        self._level = level
        self.stamps.append(stamp)
        self.index.append(level)
        self.breadth.append(share)
        self._high = max(self._high, level)
        self.depth = max(0.0, 1 - level / self._high) if self._high else 0.0
        self._advance_average()
        self._apply_hysteresis(self._classify(share))
        self.labels.append(self.regime)
        self.episode_age = (
            self.episode_age + 1
            if len(self.labels) > 1 and self.labels[-2] is self.regime
            else 0
        )
        return self.regime


def score_against(labels, benchmark, stamps, horizon=20, window=None):
    """Forward return of THE BENCHMARK, bucketed by a variant's label."""
    buckets: dict[str, list[float]] = {}
    for i, label in enumerate(labels):
        target = i + horizon
        if target >= len(benchmark) or not benchmark[i]:
            continue
        if window and not (window[0] <= stamps[i] < window[1]):
            continue
        buckets.setdefault(label.value, []).append(benchmark[target] / benchmark[i] - 1)
    return {k: sum(v) / len(v) for k, v in buckets.items() if v}


def benchmark_falls(benchmark, stamps, floor=0.20):
    """Peak-to-trough falls of the BROAD market, which are the events every
    variant is being asked to have named while they were happening."""
    episodes, peak, i = [], 0, 1
    while i < len(benchmark):
        if benchmark[i] >= benchmark[peak]:
            peak, i = i, i + 1
            continue
        trough = i
        while i < len(benchmark) and benchmark[i] < benchmark[peak]:
            if benchmark[i] < benchmark[trough]:
                trough = i
            i += 1
        if 1 - benchmark[trough] / benchmark[peak] >= floor:
            episodes.append(
                {
                    "peak": peak,
                    "trough": trough,
                    "end": min(i, len(benchmark) - 1),
                    "fall": 1 - benchmark[trough] / benchmark[peak],
                    "peak_at": stamps[peak],
                    "trough_at": stamps[trough],
                }
            )
        peak = min(i, len(benchmark) - 1)
    return episodes


def share_of_fall(labels, episode):
    first = next(
        (
            i
            for i in range(episode["peak"], episode["end"] + 1)
            if labels[i] is MarketRegime.BEAR
        ),
        None,
    )
    if first is None:
        return None
    span = episode["trough"] - episode["peak"] or 1
    return (first - episode["peak"]) / span


VARIANTS = (
    ("basket-6-equal", "equal", REFERENCE_BASKET, "the incumbent: six survivors"),
    ("all-equal", "equal", None, "every listed asset, equal weight"),
    ("all-turnover", "turnover", None, "every listed asset, weighted by turnover"),
    ("all-sqrt", "sqrt", None, "every listed asset, sqrt(turnover) weight"),
)


def main() -> int:
    limit = None
    if "--assets" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--assets") + 1])

    print("loading the archive…", flush=True)
    market = load_all(limit)
    stamps = sorted({s for series in market.values() for s in series})
    print(
        f"  {len(market)} assets · {len(stamps)} bars "
        f"{stamps[0]:%Y-%m-%d} → {stamps[-1]:%Y-%m-%d}"
    )
    turnover = turnover_averages(market)

    listed = [sum(1 for s in market.values() if stamp in s) for stamp in stamps]
    print(
        f"  listed on the first bar: {listed[0]} · on the last: {listed[-1]} "
        f"· most: {max(listed)}"
    )

    # The benchmark every variant is judged against, and the breadth the broad
    # variants read. Built once.
    print("building composites…", flush=True)
    broad = composite(market, stamps, "equal", turnover)
    broad_breadth = breadth(market, stamps, 50)
    six_breadth = breadth(market, stamps, 50, REFERENCE_BASKET)

    results = {}
    for name, weighting, universe, _note in VARIANTS:
        level = (
            broad
            if (weighting == "equal" and universe is None)
            else composite(market, stamps, weighting, turnover, universe)
        )
        share = six_breadth if universe is not None else broad_breadth
        detector = Precomputed(RegimeParameters())
        for stamp, value, wide in zip(stamps, level, share):
            detector.push(stamp, value, wide)
        results[name] = {"detector": detector, "level": level}

    falls = benchmark_falls(broad, stamps)

    print("\nDoes the label order the BROAD market's next 20 bars?")
    print("Every variant scored on the same benchmark, so a variant cannot win")
    print("by being easy to predict. Wanted: BEAR negative, BEAR < SIDEWAYS < BULL.\n")
    print(f"  {'variant':<16} {'BEAR':>8} {'SIDEWAYS':>9} {'BULL':>8}  {'ordered':>7}")
    for name, *_ in VARIANTS:
        found = score_against(results[name]["detector"].labels, broad, stamps)
        bear, side, bull = (found.get(k) for k in ("BEAR", "SIDEWAYS", "BULL"))
        ordered = None not in (bear, side, bull) and bear < side < bull
        cell = lambda v, w: f"{v:>+{w}.2%}" if v is not None else f"{'none':>{w}}"  # noqa: E731
        print(
            f"  {name:<16} {cell(bear, 8)} {cell(side, 9)} {cell(bull, 8)}  "
            f"{'YES' if ordered else 'no':>7}"
        )

    print("\nDoes BEAR arrive while the BROAD market is still falling?")
    print(f"{len(falls)} falls of 20%+ in the broad index.\n")
    print(f"  {'variant':<16} {'named':>8} {'median share of fall':>22}")
    for name, *_ in VARIANTS:
        labels = results[name]["detector"].labels
        shares = [s for e in falls if (s := share_of_fall(labels, e)) is not None]
        cell = f"{median(shares):.0%}" if shares else "--"
        print(f"  {name:<16} {len(shares):>3}/{len(falls):<4} {cell:>22}")

    print("\nBEAR share by fold. A branch that never fires trains nothing.\n")
    bounds = [
        (
            label,
            datetime.fromisoformat(a + "T00:00:00+00:00"),
            datetime.fromisoformat(b + "T00:00:00+00:00"),
        )
        for label, a, b in FOLDS
        if label != "2026-fwd"
    ]
    print("  " + f"{'variant':<16}" + "".join(f"{lb:>11}" for lb, _, _ in bounds))
    for name, *_ in VARIANTS:
        labels = results[name]["detector"].labels
        cells = ""
        for _, start, end in bounds:
            inside = [lab for s, lab in zip(stamps, labels) if start <= s < end]
            share = (
                sum(1 for x in inside if x is MarketRegime.BEAR) / len(inside)
                if inside
                else 0.0
            )
            cells += f"{share:>10.1%} "
        print(f"  {name:<16}{cells}")

    print("\nAnd the same question one fold at a time: BEAR minus BULL.")
    print("Negative is right.\n")
    print("  " + f"{'variant':<16}" + "".join(f"{lb:>11}" for lb, _, _ in bounds))
    for name, *_ in VARIANTS:
        labels = results[name]["detector"].labels
        cells = ""
        for _, start, end in bounds:
            found = score_against(labels, broad, stamps, window=(start, end))
            bear, bull = found.get("BEAR"), found.get("BULL")
            cells += (
                f"{bear - bull:>+9.2%} " if None not in (bear, bull) else f"{'--':>10} "
            )
        print(f"  {name:<16}{cells}")

    print("\n  " + "-" * 62)
    for name, _, _, note in VARIANTS:
        print(f"  {name:<16} {note}")
    print("\n  Every index above is a PROXY. True capitalisation needs circulating")
    print("  supply, which this laboratory does not hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
