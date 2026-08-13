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
import heapq
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Iterator

import numpy as np

ROOT = Path(__file__).resolve().parents[2]

# The promotion rule is the arbiter of what counts as surviving the era, and the
# search must screen on the SAME definition the record is judged by. Importing it
# rather than restating it is the point: two copies of a threshold drift, and the
# drift would show up as a search that keeps proposing candidates the rule then
# rejects -- which is exactly the loop this change exists to break.
sys.path.insert(0, str(ROOT / "orchestrator-manager"))
from quantlab_manager.promotion import (  # noqa: E402
    RESEARCH_ENDS,
    SURVIVAL_GRACE_DAYS,
)

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
BARS_PER_DAY = 288
ROUND_TRIP = 0.003
LEDGER = ROOT / "research" / "agent_runs" / "scan" / "ledger.jsonl"
STOP_FILE = ROOT / "research" / "agent_runs" / "scan" / "scan.stop"

# The book the screen simulates: three concurrent positions, and the operator's
# 25% drawdown mandate as a hard stop. Both match the real portfolio.
SLOTS = 3
MANDATE = 0.25


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
    # When each bar happened. Needed because a per-trade mean has no chronology
    # and therefore no equity path, and the equity path is where a rule dies.
    stamp: np.ndarray
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
    # Sliced to the first 19 characters: the stored form carries a `+00:00`
    # offset, and numpy parses a timezone-aware string only with a deprecation
    # warning. Every tape here is UTC already, so dropping the offset is exact
    # rather than a rounding.
    when = np.array([s[:19] for s in stamps], dtype="datetime64[s]")
    return Tape(close=prices, hour=hour, minute=minute, day_open=day_open, stamp=when)


def _entries(tape: Tape, candidate: Candidate) -> tuple[np.ndarray, np.ndarray]:
    """The bars this candidate buys on, and the return of holding from each.

    Shared by `score` and `trades` on purpose. They used to carry two copies of
    this mask, and two copies of an entry rule is one entry rule plus a future
    disagreement about what was measured.
    """
    horizon = candidate.hold_days * BARS_PER_DAY
    window = candidate.trend_days * BARS_PER_DAY
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
    return np.flatnonzero(taken), future


@dataclass(frozen=True)
class Walk:
    """What a candidate's equity did, in order. The half a mean cannot show."""

    return_pct: float
    max_drawdown: float
    breached_at: str | None
    last_trade_at: str | None
    taken: int
    # Trades the signal produced that no slot was free for. A large number here
    # means the reported path is a small sample of the signal, chosen by arrival
    # time -- which is the open question about slot allocation, visible.
    skipped: int

    @property
    def endures(self) -> bool:
        """Did it reach the end of the research era without breaching?

        Same two conditions the promotion rule applies, against the same
        constants, so a candidate that clears this screen cannot be rejected by
        the record's survival clause afterwards.
        """
        if self.breached_at is None and self.last_trade_at is None:
            return False
        if self.breached_at is not None:
            return False
        ends = np.datetime64(f"{RESEARCH_ENDS}T00:00:00", "s")
        short = (ends - np.datetime64(self.last_trade_at, "s")) / np.timedelta64(1, "D")
        return bool(short <= SURVIVAL_GRACE_DAYS)

    def document(self) -> dict[str, Any]:
        return {
            "return_pct": round(self.return_pct, 5),
            "max_drawdown": round(self.max_drawdown, 5),
            "breached_at": self.breached_at,
            "last_trade_at": self.last_trade_at,
            "taken": self.taken,
            "skipped": self.skipped,
            "endures": self.endures,
        }


def trades(
    tapes: dict[str, Tape], candidate: Candidate
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Every trade across the basket: in, out, net return, and the worst dip.

    The dip is the lowest close reached between entry and exit, relative to the
    entry price, and it is what makes a stop-loss measurable rather than
    imaginary. Without it a stop is applied to the FINAL return, which quietly
    truncates the losers while leaving intact every winner that fell through the
    stop on the way up -- hindsight, in the one place it compounds. That version
    of this function reported +167,505% over the research era, which is how it
    was caught.
    """
    entry_parts, exit_parts, return_parts, dip_parts = [], [], [], []
    horizon = candidate.hold_days * BARS_PER_DAY
    for tape in tapes.values():
        index, future = _entries(tape, candidate)
        if not len(index):
            continue
        entry_parts.append(tape.stamp[index])
        # Safe without a bounds check: `_entries` requires a finite forward
        # return, which is only true where the exit bar exists.
        exit_parts.append(tape.stamp[index + horizon])
        return_parts.append(future[index] - ROUND_TRIP)
        opened = tape.close[index]
        dip_parts.append(
            np.array(
                [
                    tape.close[i : i + horizon + 1].min() / opened[k] - 1.0
                    for k, i in enumerate(index)
                ],
                dtype=float,
            )
        )
    if not entry_parts:
        empty = np.array([], dtype="datetime64[s]")
        blank = np.array([], dtype=float)
        return empty, empty, blank, blank
    return (
        np.concatenate(entry_parts),
        np.concatenate(exit_parts),
        np.concatenate(return_parts),
        np.concatenate(dip_parts),
    )


def walk(
    entry: np.ndarray,
    exit_at: np.ndarray,
    ret: np.ndarray,
    dip: np.ndarray | None = None,
    slots: int = SLOTS,
    mandate: float = MANDATE,
    stop: float | None = None,
    stake: float | None = None,
) -> Walk:
    """Compound the trades chronologically through a three-slot book.

    **This screen approximates, in both directions, and is not a bound.** Equity
    is marked on exits only, so the drawdown it reports is what a statement at the
    end of each trade would show and never the deeper mark-to-market figure a live
    book would print. The stop fires on `dip`, the lowest CLOSE between entry and
    exit, so it exits trades that later recovered -- correct -- but a real stop
    watches the low of every bar and fills worse than the level it is set at. What
    comes out of here earns a real backtest; it does not replace one.

    `stake` is the fraction of equity committed per position, defaulting to a full
    `1/slots`. It is a parameter rather than a constant because of what the
    unparameterised version showed: of fifty-one entry rules that paid in both
    eras, all fifty-one breached the mandate, and forty-odd did it in the same
    three months of early 2018 after the book was already up more than 100%. When
    every entry rule dies in the same window, the entry rule is not what is
    killing them.

    Trades are taken first-come when a slot is free and dropped when the book is
    full. That is one of several defensible rules and is deliberately the dumbest
    one; `skipped` records how much of the signal it discarded so the choice is
    never invisible.
    """
    order = np.argsort(entry, kind="stable")
    fraction = stake if stake is not None else 1.0 / slots
    equity = peak = 1.0
    worst = 0.0
    last: str | None = None
    taken = skipped = 0
    book: list[tuple[np.datetime64, int, float, float]] = []
    seq = 0

    def close_out(until: np.datetime64 | None) -> str | None:
        """Realise every position that has exited. Returns a breach date or None."""
        nonlocal equity, peak, worst, last
        while book and (until is None or book[0][0] <= until):
            done, _, committed, outcome = heapq.heappop(book)
            equity += committed * outcome
            last = str(done)
            peak = max(peak, equity)
            drop = 1.0 - equity / peak
            worst = max(worst, drop)
            if drop >= mandate:
                return str(done)
        return None

    for i in order:
        breach = close_out(entry[i])
        if breach is not None:
            # The mandate aborts the run. Everything after this point is evidence
            # the rule never earned, and counting it would be the mistake that
            # let a system that died in 2021 be announced as the record.
            return Walk(equity - 1.0, worst, breach, last, taken, skipped)
        if len(book) >= slots:
            skipped += 1
            continue
        outcome = float(ret[i])
        if stop is not None and dip is not None and dip[i] <= -stop:
            # Stopped out on the way, whatever it did afterwards. The round trip
            # is still paid: an exit at the stop is an exit.
            outcome = -stop - ROUND_TRIP
        heapq.heappush(book, (exit_at[i], seq, equity * fraction, outcome))
        seq += 1
        taken += 1

    breach = close_out(None)
    return Walk(equity - 1.0, worst, breach, last, taken, skipped)


# How hard a losing trade is cut, and how much of the book one position may hold.
# `None` is no stop at all, kept in the grid so the search has to show that a stop
# earns its place rather than being handed it.
STOPS: tuple[float | None, ...] = (0.05, 0.08, 0.12, 0.20, None)
STAKES: tuple[float, ...] = (0.08, 0.12, 0.16, 0.20, 0.25, 1.0 / SLOTS)


def money(
    entry: np.ndarray, exit_at: np.ndarray, ret: np.ndarray, dip: np.ndarray
) -> tuple[dict[str, Any] | None, Walk | None]:
    """The sizing and stop that carry these trades through the research era.

    **Chosen on training evidence alone.** The sealed year is never consulted
    here, not even as a tiebreak: 2026 is the forward evaluation and the moment it
    picks a parameter it stops being one. So the rule is the best training return
    among the configurations that endure the era, and 2026 is told about it
    afterwards.

    Returns `(None, None)` when nothing endures, which is a result and not a
    failure -- it says the entry rule cannot be made to survive by sizing, which
    is the more useful half of what this function knows.
    """
    best: tuple[dict[str, Any], Walk] | None = None
    for stop, stake in product(STOPS, STAKES):
        walked = walk(entry, exit_at, ret, dip, stop=stop, stake=stake)
        if not walked.endures:
            continue
        if best is None or walked.return_pct > best[1].return_pct:
            best = ({"stop": stop, "stake": round(stake, 4)}, walked)
    return best if best is not None else (None, None)


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
    returns: list[np.ndarray] = []
    for tape in tapes.values():
        index, future = _entries(tape, candidate)
        if len(index):
            returns.append(future[index] - ROUND_TRIP)
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


# Where each axis stops growing. Past this the search has covered the space it
# can express, and the honest report is that it is saturated -- not another
# decimal place around a winner, which is how a grid converges on its own noise.
CEILINGS = {"thresholds": 12, "holds": 10, "trends": 10}


def axes(cycle: int) -> tuple[list[float], list[int], list[int], bool]:
    """The three parameter axes at this cycle, and whether they have saturated.

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
    if cycle >= 3:
        # Beyond here the grid must keep GROWING or the loop re-scores the same
        # points over unchanged data and writes the same answer for ever. It ran
        # nine cycles and 44,448 candidates before this, of which every one after
        # the third was a copy -- the caller passed `--cycles 3` and restarted the
        # counter at zero on every wake, so this branch was never once reached. A
        # search that cannot reach new ground is a heartbeat, not a search.
        step = cycle - 2
        thresholds = sorted({*thresholds, *(0.005 * k for k in range(1, 6 + step))})
        holds = sorted({*holds, *(12 + 4 * k for k in range(step))})
        trends = sorted({*trends, *(120 + 60 * k for k in range(step))})
    thresholds = thresholds[: CEILINGS["thresholds"]]
    holds = holds[: CEILINGS["holds"]]
    trends = trends[: CEILINGS["trends"]]
    saturated = (
        len(thresholds) == CEILINGS["thresholds"]
        and len(holds) == CEILINGS["holds"]
        and len(trends) == CEILINGS["trends"]
    )
    return thresholds, holds, trends, saturated


def grid(cycle: int) -> Iterator[Candidate]:
    """Every candidate at this cycle. Bounded, so a cycle always finishes."""
    thresholds, holds, trends, _ = axes(cycle)
    for hour, threshold, hold, trend in product(range(24), thresholds, holds, trends):
        yield Candidate(hour, threshold, hold, trend)


HOURS = tuple(range(24))
THRESHOLDS = (0.005, 0.0075, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05)
HOLDS = (1, 2, 3, 5, 7, 10)
TRENDS = (5, 10, 20, 30, 60, 90)


def neighbours(candidate: Candidate) -> list[Candidate]:
    """The candidates one step away on each axis. The unit of belief.

    A parameter set is not a discovery if its neighbours fail. Hour 8 scored
    +6.07% through the book and hour 5 scored -1.54% on a statistically identical
    signal, and the grid's best sealed candidate had a neighbour that flipped
    negative when its holding period moved by two days. Both were needles.

    A real effect is a REGION: the surrounding parameter sets agree because the
    market does not know where the grid points are. So the search ranks by what
    the neighbourhood does, and a point value is only ever a tiebreak.
    """
    axes = (
        (HOURS, "hour"),
        (THRESHOLDS, "threshold"),
        (HOLDS, "hold_days"),
        (TRENDS, "trend_days"),
    )
    out: list[Candidate] = []
    for values, name in axes:
        current = getattr(candidate, name)
        if current not in values:
            continue
        index = values.index(current)
        for step in (-1, 1):
            moved = index + step
            if 0 <= moved < len(values):
                out.append(
                    Candidate(
                        **{
                            **candidate.document(),
                            name: values[moved],
                        }
                    )
                )
    return out


def robustness(
    tapes_train: dict[str, Tape],
    tapes_forward: dict[str, Tape],
    candidate: Candidate,
) -> dict[str, Any]:
    """How the whole neighbourhood behaves, not just this point.

    `agreement` is the share of neighbours that also pay in the RESEARCH era, and
    it is the number to rank on. It used to be the share positive in both eras,
    which made the sealed year a selector; a needle is visible from training
    alone, because what makes it a needle is that its neighbours disagree, and
    the market does not know where the grid points are either way.

    `training_worst` matters just as much: a neighbourhood whose mean is positive
    because one member is spectacular is the same needle wearing an average, and
    the minimum is what exposes that. The sealed figures are carried along as a
    measurement and never enter the ordering.
    """
    family = [candidate, *neighbours(candidate)]
    training_means: list[float] = []
    sealed: list[float] = []
    agree = 0
    measured = 0
    for member in family:
        training = score(tapes_train, member)
        forward = score(tapes_forward, member)
        if training.get("n", 0) < 200 or forward.get("n", 0) < 10:
            continue
        measured += 1
        training_means.append(training["mean_net"])
        sealed.append(forward["mean_net"])
        if training["mean_net"] > 0 and training.get("t", 0.0) >= 2.0:
            agree += 1
    if not measured:
        return {"measured": 0}
    return {
        "measured": measured,
        "agreement": agree / measured,
        "training_worst": float(np.min(training_means)),
        "sealed_mean": float(np.mean(sealed)),
        "sealed_worst": float(np.min(sealed)),
    }


def survives(training: dict[str, Any], sealed: dict[str, Any]) -> bool:
    """The bar a candidate must clear to be worth six minutes of backtest.

    **Decided on the research era alone.** This used to also require the sealed
    mean to be positive, and that clause was the sealed year choosing the
    shortlist -- after which reading the best 2026 figure off that shortlist is
    selection on the answer, and the reported margin over the incumbent is partly
    the selection. 2026 is a locked forward evaluation and never feedback, and a
    filter is feedback however quietly it is spelled.

    The one thing still asked of the sealed era is a MINIMUM SAMPLE, which is a
    statement about how much evidence exists rather than about what it says: a
    configuration that takes four trades in 2026 cannot be compared with one that
    takes thirty whatever either of them returned.
    """
    return (
        training.get("n", 0) >= 200
        and sealed.get("n", 0) >= 15
        and training.get("mean_net", 0.0) > 0
        and training.get("t", 0.0) >= 3.0
    )


def cycle(tapes_train: dict[str, Tape], tapes_forward: dict[str, Tape], index: int):
    """Score every candidate in one cycle and return the survivors."""
    started = time.time()
    scored = 0
    statistical = 0
    survivors: list[dict[str, Any]] = []
    for candidate in grid(index):
        training = score(tapes_train, candidate)
        if training.get("n", 0) < 200 or training.get("mean_net", 0.0) <= 0:
            scored += 1
            continue
        sealed = score(tapes_forward, candidate)
        scored += 1
        if not survives(training, sealed):
            continue
        statistical += 1
        # The path, and only now: thirty walks per candidate is cheap, and only
        # worth paying for the ones whose per-trade statistics already hold up.
        book = trades(tapes_train, candidate)
        rule, walked = money(*book)
        if rule is None or walked is None:
            continue
        # The SAME sizing carried forward, not a second search. Refitting the
        # money management on 2026 would make the sealed figure a fit rather than
        # a measurement, which is the one thing that era exists to avoid.
        forward = walk(
            *trades(tapes_forward, candidate),
            stop=rule["stop"],
            stake=rule["stake"],
        )
        survivors.append(
            {
                **candidate.document(),
                "money": rule,
                "training": training,
                "sealed_2026": sealed,
                "training_path": walked.document(),
                "sealed_path": forward.document(),
            }
        )
    # Shortlisted by the TRAINING book, because every ordering in this function
    # has to be one the sealed year had no part in. Only the shortlist is measured
    # for robustness, since each call scores nine more candidates.
    survivors.sort(key=lambda row: -row["training_path"]["return_pct"])
    for row in survivors[:25]:
        row["robustness"] = robustness(
            tapes_train,
            tapes_forward,
            Candidate(
                row["hour"], row["threshold"], row["hold_days"], row["trend_days"]
            ),
        )
    # Ranked by NEIGHBOURHOOD, not by point value. Sorting by a point value is how
    # a needle reaches the top of this list: hour 8 scored +6.07% through the book
    # and its neighbour hour 5 scored -1.54% on a statistically identical signal.
    # Both keys are research-era figures, so the order is one the sealed year
    # could not have produced.
    survivors.sort(
        key=lambda row: (
            -row.get("robustness", {}).get("agreement", 0.0),
            -row.get("robustness", {}).get("training_worst", -1.0),
        )
    )
    return {
        "cycle": index,
        "at": datetime.now(timezone.utc).isoformat(),
        "seconds": round(time.time() - started, 1),
        # THE DENOMINATOR. The best sealed figure in this list is a maximum over
        # this many draws, and a reader who does not know the count cannot tell
        # a discovery from the tail of a distribution.
        "candidates_scored": scored,
        # The two filters kept apart, because the gap between them IS the finding:
        # how many candidates pay per trade in both eras and still cannot carry a
        # book through eight years without breaching the mandate.
        "passed_statistics": statistical,
        "survivors": len(survivors),
        "grid_saturated": axes(index)[3],
        "best": survivors[:15],
    }


def resume_from(ledger: Path) -> int:
    """The cycle after the last one the ledger recorded.

    The supervisor wakes this script every six hours with a fixed `--cycles`
    count, so without a memory the counter restarts at zero on every wake and the
    search re-scores the identical grid for ever. That is what happened: nine
    cycles logged, all of them 0, 1 or 2, and the widening branch at cycle 3 was
    never once reached. Progress that lives only in a process variable is lost
    the moment the process is the thing that restarts.
    """
    last = -1
    try:
        with ledger.open() as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = max(last, int(json.loads(line)["cycle"]))
                except (ValueError, KeyError, TypeError):
                    continue
    except FileNotFoundError:
        return 0
    return last + 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--cycles",
        type=int,
        default=1,
        help="0 runs until the stop file appears; otherwise this many cycles",
    )
    parser.add_argument("--ledger", default=str(LEDGER))
    parser.add_argument(
        "--from-cycle",
        type=int,
        default=None,
        help="start here instead of continuing the ledger's last cycle",
    )
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
    index = args.from_cycle if args.from_cycle is not None else resume_from(ledger)
    while True:
        if STOP_FILE.exists():
            print(f"stop file present: {STOP_FILE}")
            return 0
        report = cycle(tapes_train, tapes_forward, index)
        with ledger.open("a") as handle:
            handle.write(json.dumps(report) + "\n")
        print(
            f"cycle {index}: {report['candidates_scored']:,} scored in "
            f"{report['seconds']}s, {report['passed_statistics']} paid in both "
            f"eras, {report['survivors']} also carried a book to "
            f"{RESEARCH_ENDS}"
            + (" [grid saturated]" if report["grid_saturated"] else ""),
            flush=True,
        )
        for row in report["best"][:5]:
            path, forward, rule = (
                row["training_path"],
                row["sealed_path"],
                row["money"],
            )
            stop = "none" if rule["stop"] is None else f"{rule['stop']:.0%}"
            print(
                f"   hour {row['hour']:>2} thr {row['threshold']:.3f} "
                f"hold {row['hold_days']}d trend {row['trend_days']}d "
                f"stake {rule['stake']:.0%} stop {stop}  "
                f"| training {path['return_pct']:+.1%} maxDD "
                f"{path['max_drawdown']:.1%} to {str(path['last_trade_at'])[:10]} "
                f"| 2026 {forward['return_pct']:+.1%} maxDD "
                f"{forward['max_drawdown']:.1%} ({forward['taken']} trades)",
                flush=True,
            )
        index += 1
        if args.cycles and index >= args.cycles:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
