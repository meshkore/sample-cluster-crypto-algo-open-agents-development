"""The teacher: what a perfect-hindsight long-only trader would have held.

**The claim this encodes.** Buy-and-hold from 10 to 30 is +200%. A trader who
caught every clean swing on the way up — long from each significant trough,
flat over each significant decline — compounded far more on the same tape. In
log-wealth that is exact and additive: a position open from bar `b` to bar `s`
earns `log(close[s]) - log(close[b])`, which is the sum of the one-bar log
returns while it is open, whatever the path in between. So the compounded return
of a set of non-overlapping long trades is

    sum over held transitions i of ( log close[i] - log close[i-1] ).

Maximising that, long-only, is: **be in the market during every up-swing and
flat during every down-swing.** With a minimum per-swing size (start: 1% gross)
to drop noise too small to be a real trade, that is exactly a threshold zigzag —
alternating significant troughs and peaks, each leg at least `threshold` from the
last pivot. Holding runs from each confirmed trough to the next confirmed peak.

The oracle sees the whole series — that is the point, and it is only ever the
**training target**, never a feature. Its compounded return is the unreachable
ceiling; the whole experiment is how much of it a net that sees only the past
can keep.

`_reference` is the readable definition and the oracle the fast path (if one is
ever added) must match — kept here, not in the test file, because a definition
that lives only in a test gets edited to match the code the day they disagree.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Pivot:
    """A confirmed reversal: a significant trough (`low`) or peak (`high`)."""

    index: int
    price: float
    kind: str  # "low" | "high"


def zigzag_pivots(close: np.ndarray, threshold: float = 0.01) -> list[Pivot]:
    """Alternating significant troughs and peaks, each leg >= `threshold` gross.

    A single forward pass, and three boundary rules a teacher with full hindsight
    must get right — each one was a wrong label the first time this was written:

    - **The first pivot is emitted, not skipped.** The walk starts undecided,
      tracking the running low AND high from bar 0. The first move that clears
      `threshold` confirms the extreme it moved *away from* as the opening pivot
      (a rise confirms the running low; a fall confirms the running high), so the
      opening leg is never lost.
    - **The final leg is closed at the last bar.** The oracle knows the whole
      series, so the running extreme of the leg still open when the tape ends is
      a real pivot — otherwise a monotonic rise with no pullback earns nothing,
      which is the opposite of what a perfect trader does.
    - **Every confirmed leg has moved at least `threshold`**, so every up-leg is a
      trade that clears the size floor by construction.
    """
    close = np.asarray(close, dtype=float)
    n = len(close)
    if n == 0:
        return []

    pivots: list[Pivot] = []
    hi_idx, hi_price = 0, close[0]  # running high since the last pivot / start
    lo_idx, lo_price = 0, close[0]  # running low since the last pivot / start
    direction = 0  # 0 undecided, +1 rising (seeking a peak), -1 falling (seeking a trough)

    for i in range(1, n):
        price = close[i]
        if price >= hi_price:
            hi_idx, hi_price = i, price
        if price <= lo_price:
            lo_idx, lo_price = i, price

        if direction >= 0 and price <= hi_price * (1.0 - threshold):
            # Rising or undecided leg reverses down: the running high is a peak.
            pivots.append(Pivot(hi_idx, hi_price, "high"))
            direction = -1
            lo_idx, lo_price = i, price  # a fresh low leg starts here
        elif direction <= 0 and price >= lo_price * (1.0 + threshold):
            # Falling or undecided leg reverses up: the running low is a trough.
            pivots.append(Pivot(lo_idx, lo_price, "low"))
            direction = +1
            hi_idx, hi_price = i, price  # a fresh high leg starts here

    # Close the leg still open when the tape ends, resolved by hindsight.
    if direction > 0:
        pivots.append(Pivot(hi_idx, hi_price, "high"))
    elif direction < 0:
        pivots.append(Pivot(lo_idx, lo_price, "low"))
    return pivots


def holding_labels(close: np.ndarray, threshold: float = 0.01) -> np.ndarray:
    """1 where a perfect trader is long *at that bar*, 0 where flat — one bit/bar.

    `label[i] == 1` means the position is open at bar `i`, so the return earned
    over the next transition (`close[i+1]/close[i]`) is captured. Long from each
    confirmed trough (**inclusive**) to the bar **before** the next confirmed peak
    — the peak is exclusive because you sell *at* the peak and own nothing after
    it. That one-bar boundary is the whole ball game: mark the peak inclusive and
    two adjacent up-legs touch, so the position is held straight through the
    decline between them and the compounded return collapses to buy-and-hold.
    """
    close = np.asarray(close, dtype=float)
    n = len(close)
    label = np.zeros(n, dtype=np.int8)
    pivots = zigzag_pivots(close, threshold)
    for a, b in zip(pivots, pivots[1:]):
        if a.kind == "low" and b.kind == "high":
            label[a.index : b.index] = 1  # peak exclusive: flat during the decline
    return label


def oracle_return(close: np.ndarray, label: np.ndarray) -> float:
    """The compounded return of holding exactly where `label` is 1.

    Close-to-close over held transitions — the idealised ceiling, before the
    next-open fill and the 0.30% toll a real trade pays. Its distance from what
    the net achieves is the whole measurement, so it is reported, not hidden.
    """
    close = np.asarray(close, dtype=float)
    label = np.asarray(label)
    log_ret = np.zeros(len(close))
    log_ret[1:] = np.diff(np.log(close))
    held = label[:-1]  # holding over transition i means being long at bar i-1
    return float(np.exp(np.sum(log_ret[1:] * held)) - 1.0)


def _reference(close: np.ndarray, threshold: float = 0.01) -> np.ndarray:
    """The rule as a plain state machine: the definition `holding_labels` restates.

    Walks the confirmed pivots and marks every trough-to-peak leg as held, peak
    exclusive. Slow and obvious on purpose; kept as the readable statement of the
    label the vectorised path must reproduce.
    """
    pivots = zigzag_pivots(close, threshold)
    label = np.zeros(len(close), dtype=np.int8)
    holding = False
    trough = 0
    for pivot in pivots:
        if pivot.kind == "low":
            holding, trough = True, pivot.index
        elif pivot.kind == "high" and holding:
            label[trough : pivot.index] = 1
            holding = False
    return label


def trade_count(label: np.ndarray) -> int:
    """Contiguous holding runs — one round trip each, including a run at bar 0."""
    label = np.asarray(label, dtype=int)
    if len(label) == 0:
        return 0
    starts = int(label[0]) + int(np.sum((label[1:] == 1) & (label[:-1] == 0)))
    return starts


def summarise(close: np.ndarray, threshold: float = 0.01) -> dict[str, float]:
    """The ceiling this teacher sets, next to buy-and-hold and its own coverage."""
    label = holding_labels(close, threshold)
    buy_hold = float(close[-1] / close[0] - 1.0) if len(close) else 0.0
    trades = trade_count(label)
    return {
        "bars": int(len(close)),
        "threshold": threshold,
        "trades": trades,
        "time_in_market": float(np.mean(label)) if len(label) else 0.0,
        "buy_hold_return": buy_hold,
        "oracle_return": oracle_return(close, label),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--threshold", type=float, default=0.01)
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="15m")
    args = parser.parse_args(argv)

    from .dataset import Dataset

    dataset = Dataset(args.data_root, symbols=[args.symbol], interval=args.interval)
    research = dataset.research()
    bars = research[args.symbol]
    close = np.array([b.close for b in bars], dtype=float)

    stats = summarise(close, args.threshold)
    print(f"symbol            {args.symbol} {args.interval}")
    print(f"bars              {stats['bars']:,}")
    print(f"threshold         {stats['threshold']:.2%}")
    print(f"oracle trades     {stats['trades']:,}")
    print(f"time in market    {stats['time_in_market']:.1%}")
    print(f"buy & hold        {stats['buy_hold_return']:+,.1%}")
    print(f"ORACLE CEILING    {stats['oracle_return']:+,.2%}   (close-to-close, pre-cost)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
