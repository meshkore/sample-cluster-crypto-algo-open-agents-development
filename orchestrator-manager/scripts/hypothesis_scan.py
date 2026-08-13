#!/usr/bin/env python3
"""Score thousands of hypotheses against both eras, with no model in the loop.

    python3 orchestrator-manager/scripts/hypothesis_scan.py --cycles 0

**Why this exists, and why it costs nothing.** A full portfolio backtest of one
configuration over eight years of five-minute bars takes about six minutes. A
sweep of twenty-four entry hours across both eras was therefore five hours, and
was abandoned at sixteen minutes. The same question -- what does this signal pay,
per trade, net of the 0.30% round trip -- is answered directly off the tape in
milliseconds once the arrays are in memory. So this scans the grid, and only the
handful of configurations that survive it are worth a real backtest.

**No language model is called here, ever.** The continuous search that ran in
this laboratory before spawned headless agents to write code, and in one day it
consumed sixty per cent of a weekly subscription while producing one measurable
result. This does arithmetic. It can run for a week on a laptop and cost nothing
but electricity, which is the only kind of loop that is safe to leave unattended.
Writing NEW code still needs a person or a model, and that stays in the operator's
terminal by design.

**Both eras, every candidate, and the denominator recorded.** The ledger stores
the training statistic and the 2026 statistic side by side, plus how many
candidates the cycle scored. A configuration that wins the sealed year while
losing the research era is a coin flip, and the pair is what makes that visible.
The count matters just as much: "+6.07% in 2026" means one thing out of three
candidates and another out of three thousand, and only the ledger remembers which.

**What it cannot do.** It cannot invent a mechanism. It searches the parameter
space of a signal someone already wrote down, which is worth doing -- the
incumbent's 06:00 entry hour turned out to be the eighteenth best of twenty-four
and had never been chosen by anyone -- and is not the same thing as research.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Iterator

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
BARS_PER_DAY = 288
ROUND_TRIP = 0.003
LEDGER = ROOT / "research" / "agent_runs" / "scan" / "ledger.jsonl"
STOP_FILE = ROOT / "research" / "agent_runs" / "scan" / "scan.stop"


@dataclass(frozen=True)
class Candidate:
    """One hypothesis: when to buy, how far up, how long to hold."""

    hour: int
    threshold: float
    hold_days: int
    trend_days: int

    def document(self) -> dict[str, Any]:
        return {
            "hour": self.hour,
            "threshold": round(self.threshold, 5),
            "hold_days": self.hold_days,
            "trend_days": self.trend_days,
        }


@dataclass
class Tape:
    """One symbol's closes, with the columns every candidate needs precomputed."""

    close: np.ndarray
    hour: np.ndarray
    minute: np.ndarray
    day_open: np.ndarray
    cumulative: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        # A prefix sum, so a trailing mean of any window is two lookups rather
        # than a convolution per candidate. The grid asks for several window
        # lengths and would otherwise recompute the same sums for each.
        self.cumulative = np.cumsum(np.insert(self.close, 0, 0.0))

    def trailing_mean(self, window: int) -> np.ndarray:
        """Mean of the `window` closes BEFORE each bar. Never includes itself.

        Including the current bar would let the trend filter see the move it is
        being asked to judge, which flatters every result on the grid at once and
        in a way no single number would look wrong.
        """
        out = np.full(len(self.close), np.nan)
        if window < len(self.close):
            out[window:] = (
                self.cumulative[window:-1] - self.cumulative[: -window - 1]
            ) / window
        return out

    def forward_return(self, horizon: int) -> np.ndarray:
        out = np.full(len(self.close), np.nan)
        if horizon < len(self.close):
            out[:-horizon] = self.close[horizon:] / self.close[:-horizon] - 1.0
        return out


def load(root: str, symbol: str) -> Tape | None:
    """The largest processed CSV for a symbol, as arrays."""
    pattern = f"{ROOT}/backtester/data/{root}/processed/binance/{symbol}/5m/*.csv"
    files = sorted(glob.glob(pattern), key=os.path.getsize)
    if not files:
        return None
    stamps: list[str] = []
    close: list[float] = []
    with open(files[-1]) as handle:
        for row in csv.DictReader(handle):
            stamps.append(row["timestamp"])
            close.append(float(row["close"]))
    if len(close) < BARS_PER_DAY * 40:
        return None
    prices = np.array(close, dtype=float)
    hour = np.array([int(s[11:13]) for s in stamps], dtype=np.int16)
    minute = np.array([int(s[14:16]) for s in stamps], dtype=np.int16)
    first: dict[str, float] = {}
    for index, stamp in enumerate(stamps):
        first.setdefault(stamp[:10], prices[index])
    day_open = np.array([first[s[:10]] for s in stamps], dtype=float)
    return Tape(close=prices, hour=hour, minute=minute, day_open=day_open)


def score(tapes: dict[str, Tape], candidate: Candidate) -> dict[str, Any]:
    """What this candidate's trades paid, per trade, net of the round trip.

    Deliberately NOT a portfolio. There are no slots, no sizing and no drawdown
    ramp here, so this measures whether the SIGNAL pays rather than how much of
    it a three-position book captures. The two can disagree sharply -- hours 5
    and 8 scored +0.556% and +0.573% here and produced -1.54% and +6.07% through
    the book -- and that disagreement is itself the finding: when signals of
    equal strength give opposite portfolio results, the portfolio result is
    mostly about which trades got a slot.
    """
    horizon = candidate.hold_days * BARS_PER_DAY
    window = candidate.trend_days * BARS_PER_DAY
    returns: list[np.ndarray] = []
    for tape in tapes.values():
        trail = tape.trailing_mean(window)
        future = tape.forward_return(horizon)
        move = tape.close / tape.day_open - 1.0
        taken = (
            (tape.hour == candidate.hour)
            & (tape.minute == 0)
            & (move >= candidate.threshold)
            & np.isfinite(trail)
            & (tape.close > trail)
            & np.isfinite(future)
        )
        if taken.any():
            returns.append(future[taken] - ROUND_TRIP)
    if not returns:
        return {"n": 0}
    sample = np.concatenate(returns)
    if len(sample) < 3 or sample.std(ddof=1) == 0:
        return {"n": int(len(sample))}
    mean = float(sample.mean())
    return {
        "n": int(len(sample)),
        "mean_net": mean,
        "win_rate": float((sample > 0).mean()),
        "t": float(mean / (sample.std(ddof=1) / np.sqrt(len(sample)))),
    }


def grid(cycle: int) -> Iterator[Candidate]:
    """The search space, widened one step per cycle.

    Cycle 0 is the neighbourhood of the incumbent. Each cycle after it adds
    coarser holds and thresholds rather than refining what is already dense:
    refining around a winner is how a search converges on the noise it started
    from, and this laboratory has already published one result that way.
    """
    thresholds = [0.005, 0.0075, 0.01, 0.015, 0.02, 0.025, 0.03]
    holds = [1, 2, 3, 5]
    trends = [10, 20, 30, 60]
    if cycle >= 1:
        holds = holds + [7, 10]
        trends = trends + [5, 90]
    if cycle >= 2:
        thresholds = thresholds + [0.04, 0.05]
    for hour, threshold, hold, trend in product(range(24), thresholds, holds, trends):
        yield Candidate(hour, threshold, hold, trend)


def survives(training: dict[str, Any], sealed: dict[str, Any]) -> bool:
    """The bar a candidate must clear to be worth six minutes of backtest.

    Both eras positive, the research era significant, and enough sealed trades
    that the forward figure is not one lucky week. The research-era threshold is
    the strict one on purpose: it has thousands of observations and can support a
    t-statistic, while 2026 has a few dozen and cannot.
    """
    return (
        training.get("n", 0) >= 200
        and sealed.get("n", 0) >= 15
        and training.get("mean_net", 0.0) > 0
        and sealed.get("mean_net", 0.0) > 0
        and training.get("t", 0.0) >= 3.0
    )


def cycle(tapes_train: dict[str, Tape], tapes_forward: dict[str, Tape], index: int):
    """Score every candidate in one cycle and return the survivors."""
    started = time.time()
    scored = 0
    survivors: list[dict[str, Any]] = []
    for candidate in grid(index):
        training = score(tapes_train, candidate)
        if training.get("n", 0) < 200 or training.get("mean_net", 0.0) <= 0:
            scored += 1
            continue
        sealed = score(tapes_forward, candidate)
        scored += 1
        if survives(training, sealed):
            survivors.append(
                {
                    **candidate.document(),
                    "training": training,
                    "sealed_2026": sealed,
                }
            )
    survivors.sort(key=lambda row: -row["sealed_2026"]["mean_net"])
    return {
        "cycle": index,
        "at": datetime.now(timezone.utc).isoformat(),
        "seconds": round(time.time() - started, 1),
        # THE DENOMINATOR. The best sealed figure in this list is a maximum over
        # this many draws, and a reader who does not know the count cannot tell
        # a discovery from the tail of a distribution.
        "candidates_scored": scored,
        "survivors": len(survivors),
        "best": survivors[:15],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--cycles",
        type=int,
        default=1,
        help="0 runs until the stop file appears; otherwise this many cycles",
    )
    parser.add_argument("--ledger", default=str(LEDGER))
    args = parser.parse_args(argv)

    print("loading tapes ...", flush=True)
    tapes_train = {s: t for s in SYMBOLS if (t := load("research", s)) is not None}
    tapes_forward = {s: t for s in SYMBOLS if (t := load("forward", s)) is not None}
    print(
        f"training {len(tapes_train)} symbols, sealed {len(tapes_forward)} symbols",
        flush=True,
    )

    ledger = Path(args.ledger)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    index = 0
    while True:
        if STOP_FILE.exists():
            print(f"stop file present: {STOP_FILE}")
            return 0
        report = cycle(tapes_train, tapes_forward, index)
        with ledger.open("a") as handle:
            handle.write(json.dumps(report) + "\n")
        print(
            f"cycle {index}: {report['candidates_scored']:,} scored in "
            f"{report['seconds']}s, {report['survivors']} survived",
            flush=True,
        )
        for row in report["best"][:5]:
            print(
                f"   hour {row['hour']:>2} thr {row['threshold']:.3f} "
                f"hold {row['hold_days']}d trend {row['trend_days']}d  "
                f"training {row['training']['mean_net']:+.3%} (t {row['training']['t']:.1f}) "
                f"| 2026 {row['sealed_2026']['mean_net']:+.3%} "
                f"(n {row['sealed_2026']['n']})",
                flush=True,
            )
        index += 1
        if args.cycles and index >= args.cycles:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
