"""What is the major-trend detector actually saying, and when does it say it?

H-L077D measured that the detector labels 11 of 731 bars BEAR in the fold that
falls, and 0.0% of the fold before it. A bear-market bounce strategy cannot be
selected by a search whose bear branch is switched on for 1.5% of the tape, so
the detector -- not the bounce rule -- is the binding constraint.

This does NOT run the backtester. It reads the six reference CSVs straight off
disk, rebuilds the same equal-weighted composite `MarketDetector` builds, and
feeds `observe()` bar by bar. That makes a full 2017-2026 pass cost under a
second, which is what lets a parameter grid be measured rather than argued
about. The detector class is imported, never reimplemented: if this script and
the router disagree, the script is wrong.

Three questions, in the order that matters:

  1. SHARE -- how much of each fold does each label cover? A label that never
     fires trains nothing.
  2. SEPARATION -- does the label order the forward return of the composite?
     BULL > SIDEWAYS > BEAR, or the detector is decorative.
  3. LAG -- for every real drawdown of the composite, how many bars after the
     peak does BEAR arrive, and how far into the fall is that? A detector that
     calls BEAR at the bottom is worse than one that never calls it, because
     the strategy it enables trades the recovery as if it were the crash.

    python3 orchestrator-manager/scripts/detector_diagnosis.py
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

from quantlab_trading.regime import (
    REFERENCE_BASKET,
    MarketDetector,
    MarketRegime,
    RegimeParameters,
)


def candle_root() -> Path:
    """Where the daily bars actually live.

    The repository carries only the six reference assets -- enough to reason
    about the market-wide detector and nothing else. The full archive of 386 is
    downloaded data and is deliberately NOT committed, so it sits in the runtime
    workspace. Preferring the runtime means the same script answers a question
    about six assets or about all of them depending on what the machine holds,
    rather than silently answering the small version of the question.
    """
    for candidate in (
        Path.home()
        / "Library/Application Support/QuantLab/data/research/processed/binance",
        Path(__file__).resolve().parents[2]
        / "backtester/data/research/processed/binance",
    ):
        if candidate.is_dir():
            return candidate
    raise SystemExit("no candle archive found; run a download first")


CANDLES = candle_root()

FOLDS = [
    ("2018-2020", "2018-01-01", "2020-01-01"),
    ("2020-2022", "2020-01-01", "2021-12-31"),
    ("2022-2024", "2021-12-31", "2024-01-01"),
    ("2024-2026", "2024-01-01", "2025-12-31"),
    ("2026-fwd", "2026-01-01", "2027-01-01"),
]


def load(symbol: str) -> dict[datetime, float]:
    """Closes by timestamp for one reference asset.

    The processed directory holds one CSV per (symbol, timeframe) named by a
    content hash. There is exactly one per symbol here; if that ever stops
    being true the sorted-first choice is deterministic rather than arbitrary.
    """
    folder = CANDLES / symbol / "1d"
    files = sorted(folder.glob("*.csv"))
    if not files:
        raise SystemExit(f"no candles for {symbol} under {folder}")
    out: dict[datetime, float] = {}
    with files[0].open() as handle:
        for row in csv.DictReader(handle):
            close = float(row["close"])
            if close > 0:
                out[datetime.fromisoformat(row["timestamp"])] = close
    return out


def trailing_average(series: list[float], period: int) -> list[float | None]:
    """The same simple average the backtester serves as `sma_<period>`."""
    out: list[float | None] = []
    total = 0.0
    for position, value in enumerate(series):
        total += value
        if position >= period:
            total -= series[position - period]
        out.append(total / period if position >= period - 1 else None)
    return out


def tape(breadth_period: int = 200):
    """Every bar of the reference basket, with the breadth flag precomputed.

    Returns `(timestamp, closes, above_trend)` triples in time order -- exactly
    the three arguments `MarketDetector.observe` takes from the router, so the
    detector cannot tell it is being driven by a script.
    """
    closes = {symbol: load(symbol) for symbol in REFERENCE_BASKET}
    averages: dict[str, dict[datetime, float | None]] = {}
    for symbol, series in closes.items():
        stamps = sorted(series)
        values = [series[s] for s in stamps]
        averages[symbol] = dict(zip(stamps, trailing_average(values, breadth_period)))

    moments = sorted({stamp for series in closes.values() for stamp in series})
    for moment in moments:
        bar = {s: closes[s][moment] for s in REFERENCE_BASKET if moment in closes[s]}
        above = {
            s: bar[s] > average
            for s in bar
            if (average := averages[s].get(moment)) is not None
        }
        yield moment, bar, above


def run(parameters: RegimeParameters, rows) -> MarketDetector:
    detector = MarketDetector(parameters)
    for moment, closes, above in rows:
        detector.observe(moment, closes, above)
    return detector


def shares(
    detector: MarketDetector, start: datetime, end: datetime
) -> dict[str, float]:
    labels = [
        label
        for stamp, label in zip(detector.stamps, detector.labels)
        if start <= stamp < end
    ]
    total = len(labels) or 1
    return {
        regime.value: sum(1 for label in labels if label is regime) / total
        for regime in MarketRegime
    }


def drawdowns(detector: MarketDetector, floor: float = 0.20) -> list[dict]:
    """Every peak-to-trough fall of the composite worth at least `floor`.

    Found on the recorded composite after the fact, which is exactly the point:
    these are the falls the detector was supposed to have named while they were
    happening.
    """
    index, stamps = detector.index, detector.stamps
    episodes: list[dict] = []
    peak_position = 0
    position = 1
    while position < len(index):
        if index[position] >= index[peak_position]:
            peak_position = position
            position += 1
            continue
        trough_position = position
        while position < len(index) and index[position] < index[peak_position]:
            if index[position] < index[trough_position]:
                trough_position = position
            position += 1
        fall = 1 - index[trough_position] / index[peak_position]
        if fall >= floor:
            episodes.append(
                {
                    "peak": peak_position,
                    "trough": trough_position,
                    "recovered": min(position, len(index) - 1),
                    "fall": fall,
                    "peak_at": stamps[peak_position],
                    "trough_at": stamps[trough_position],
                }
            )
        peak_position = min(position, len(index) - 1)
    return episodes


def lag(detector: MarketDetector, episode: dict) -> dict:
    """When did BEAR arrive, relative to the fall it was meant to name?

    `share_of_fall` is the fraction of the peak-to-trough distance already lost
    by the time the label turns. Above 1.0 means the label arrived after the
    bottom -- the strategy it enables is short the recovery.
    """
    labels = detector.labels
    first = next(
        (
            position
            for position in range(episode["peak"], episode["recovered"] + 1)
            if labels[position] is MarketRegime.BEAR
        ),
        None,
    )
    if first is None:
        return {"called": False}
    span = episode["trough"] - episode["peak"] or 1
    return {
        "called": True,
        "bars_after_peak": first - episode["peak"],
        "bars_after_trough": first - episode["trough"],
        "share_of_fall": (first - episode["peak"]) / span,
        "at": detector.stamps[first],
    }


def report(name: str, parameters: RegimeParameters, rows) -> MarketDetector:
    detector = run(parameters, rows)
    print(f"\n=== {name} ===")
    print(
        f"trend {parameters.trend_period} · slope {parameters.slope_period} · "
        f"breadth {parameters.bear_breadth}/{parameters.bull_breadth} "
        f"on {parameters.breadth_key} · confirm {parameters.confirmation_bars}"
    )

    print("\n  label share by fold")
    print(f"    {'fold':<12} {'UNKNOWN':>8} {'BEAR':>8} {'SIDEWAYS':>9} {'BULL':>8}")
    for label, start, end in FOLDS:
        found = shares(
            detector,
            datetime.fromisoformat(start + "T00:00:00+00:00"),
            datetime.fromisoformat(end + "T00:00:00+00:00"),
        )
        print(
            f"    {label:<12} {found['UNKNOWN']:>7.1%} {found['BEAR']:>8.1%} "
            f"{found['SIDEWAYS']:>9.1%} {found['BULL']:>8.1%}"
        )

    print("\n  does the label order the future? (20-bar forward composite return)")
    for label, stats in detector.separation().items():
        print(
            f"    {label:<9} {stats['mean_forward_return']:>+8.2%} over "
            f"{int(stats['bars']):>5} bars · {stats['positive_share']:.0%} positive"
        )

    print("\n  every fall of 20% or more, and when BEAR was called")
    for episode in drawdowns(detector):
        timing = lag(detector, episode)
        head = (
            f"    {episode['peak_at']:%Y-%m-%d} -> {episode['trough_at']:%Y-%m-%d} "
            f"{episode['fall']:>6.1%}"
        )
        if not timing["called"]:
            print(f"{head}  never called")
            continue
        print(
            f"{head}  BEAR at {timing['at']:%Y-%m-%d}, "
            f"{timing['bars_after_peak']:>4} bars after the peak "
            f"({timing['share_of_fall']:>5.0%} of the fall already gone)"
        )
    return detector


def main() -> int:
    rows = list(tape())
    report("incumbent", RegimeParameters(), rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
