#!/usr/bin/env python3
"""A search that learns to search, and publishes whatever beats the champion.

    python3 orchestrator-manager/scripts/arena.py --rounds 0

**What is self-improving here, precisely.** Two things, and neither of them is
the strategy rewriting its own source.

1. *A surrogate model of the objective.* Every genome the arena has ever
   evaluated goes into an archive with the score it earned. Each round a
   gradient-boosted regressor is fitted on that archive and used to rank fifteen
   hundred proposals, of which only the top forty are actually measured. The
   archive grows every round, so the model gets better at guessing which genomes
   are worth measuring, so the same wall-clock buys more good candidates. That
   is the efficiency that improves, and it is MEASURED rather than asserted:
   `rank_correlation` in every round's ledger line is the Spearman correlation
   between what the model predicted for that round's forty and what they turned
   out to be -- computed before the truth was known, so it is honestly
   out-of-sample.

2. *An evolving population.* Elites are kept, crossed and mutated; a fifth of
   each generation is random immigrants so the surrogate cannot trap the search
   in the neighbourhood it already understands.

**No language model is called here, ever.** The loop that ran in this laboratory
before spawned headless agents to write code and consumed sixty per cent of a
weekly subscription in one day for one measurable result. This is numpy and
scikit-learn over a CSV. It can run for a week on a laptop and cost electricity,
which is the only kind of loop that is safe to leave unattended.

**What it optimises.** `quality.score` -- the geometric mean of growth, the
return of whoever bought at the very peak, maximum drawdown, time spent
underwater, the longest run of losing months, and whether the growth is a line
or a spike -- plus two terms this file adds, each with its own veto, in the same
geometric mean and for the same reason as the other six.

`consistent` -- the share of four contiguous two-year folds of the research era
in which the genome scores at all. A system that made everything it ever made in
2021 has a fine whole-era curve, and no whole-era measure can tell it apart from
one that worked throughout.

`frequent` -- round trips a year over the research era, against a floor derived
from how LONG the sealed window is. A rule that trades ten times a year takes
about six in seven months, which is not enough to judge it forward -- so it can
never be promoted, and a search that converges on such rules runs for days and
publishes nothing. That is not hypothetical: the arena's first live round found
a genome scoring 0.566, past the champion and past the floor, that would have
taken NO trades at all in 2026.

**2026 is never feedback.** The sealed tape is loaded, and it is asked exactly
one question: how many trades would this genome have taken. That is a statement
about how much evidence exists, not about what the evidence says, and it is the
same clause `hypothesis_scan.survives` already applies. No sealed RETURN reaches
any ranking, threshold or promotion decision in this file. The forward backtest
that follows a promotion is a measurement published beside the training one.

**What a promotion costs and why it is rare.** Beating the champion's screen
fitness by `PROMOTION_MARGIN` triggers two real five-minute-resolution backtests
-- the training half and the sealed half, identical but for `trade_from` --
which take about twelve minutes together and appear on the public board as a
pair. `DAILY_PROMOTIONS` caps them, because a board with sixty near-identical
cards on it is a board nobody reads.

**The screen is not the backtest.** Fitness comes from the fast tape screen in
`hypothesis_scan`: three slots, first-come allocation, a percentage stop on the
lowest close, no order book. The real engine has ATR stops, a trend filter that
warms, per-bar accounting and a market gate. They disagree, and when they do the
backtest is right. The screen's job is to decide what deserves twelve minutes.

Stop it with:   touch research/agent_runs/arena/arena.stop
Watch it with:  tail -f research/agent_runs/arena/arena.log
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "orchestrator-manager"))


def _load_scan():
    """Import `hypothesis_scan` as a module.

    It is a script by filename and a library by content -- the tape loader, the
    trade builder and the equity walk all live in it, and re-implementing any of
    them here would give the arena a second definition of what a trade is. The
    laboratory has been bitten by exactly that before: a screen and a promotion
    rule measuring different things kept proposing candidates the rule rejected.
    """
    path = Path(__file__).resolve().parent / "hypothesis_scan.py"
    spec = importlib.util.spec_from_file_location("hypothesis_scan", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["hypothesis_scan"] = module
    spec.loader.exec_module(module)
    return module


hs = _load_scan()

ARENA = ROOT / "research" / "agent_runs" / "arena"
ARCHIVE = ARENA / "archive.jsonl"
LEDGER = ARENA / "rounds.jsonl"
CHAMPION = ARENA / "champion.json"
STOP_FILE = ARENA / "arena.stop"

# How much better than the reigning champion a genome must screen before it is
# worth twenty-four minutes of real backtest and a card on the public board.
#
# Ten per cent RELATIVE, not absolute. The board is ranked on a number that lives
# between 0 and 1 and whose realistic range is 0.2 to 0.6, so a fixed margin is
# either meaningless at the top or impassable at the bottom.
PROMOTION_MARGIN = 1.10

# The board is for reading. Sixty cards a day differing in the fourth decimal is
# not a record of progress, it is a denial-of-service on the operator's attention.
DAILY_PROMOTIONS = 8

# How many genomes the surrogate ranks, and how many of those are measured.
#
# The ratio is the whole point: proposing is free and measuring is not, so the
# model spends its accuracy on throwing away the 97% that were never going to
# score. `IMMIGRANTS` are measured WITHOUT consulting the model at all -- a
# surrogate trained only on what the surrogate chose will confirm itself for
# ever, and the archive would stop being a fair sample of the space.
PROPOSALS = 1500
MEASURED = 40
IMMIGRANTS = 10

# Contiguous folds of the research era. Four, so each is about two years -- long
# enough to contain a real regime and short enough that a single bull run cannot
# carry all of them.
FOLDS = 4

# The system the arena has to beat, as a genome.
#
# `gate-40 thr-2.5pct`, published 2026-08-15: +353% over the research era, an
# 18.7% maximum drawdown, and 4.6% below its own high at the end. It is the best
# thing on the board, and without it here the arena's first round would find
# something better than nothing and promote it, then something better than that,
# and the board would fill with cards that never had to clear the bar that
# already existed.
#
# Measured through the arena's OWN screen rather than carried across from the
# backtest, because a floor in different units is not a floor. The screen and the
# engine disagree -- three slots and a percentage stop against ATR stops and
# per-bar accounting -- so the incumbent's screen fitness is the only number a
# challenger's screen fitness can honestly be compared with.
#
# **Only the SIGNAL is fixed here.** The money management is searched, over the
# same axes every challenger gets, and the floor is the best the incumbent's
# signal can be made to do. The first version of this pinned the incumbent's
# sizing too -- a full stake with no stop, which is what `risk_per_trade=0.05`
# comes to in the real engine -- and the screen killed it on 1918-01-20, twenty
# days in, for a 27.4% mark-to-market drawdown. The engine records 18.7% for the
# same system, because the screen carries every open position at its worst point
# simultaneously and the engine does not. A floor built on one instrument's
# pessimism about one arbitrary sizing is not a floor, it is a rounding error.
INCUMBENT_SIGNAL = {
    "hour": 6,
    "threshold": 0.025,
    # `maximum_holding_bars=864` at 288 bars a day.
    "hold_days": 3,
    "trend_days": 30,
}

# The bar a first challenger must clear even if the incumbent screens at nothing.
#
# It can: see above. Without this the arena's opening round would find a genome
# better than zero and publish it, which is how a board fills with cards that
# never had to beat anything. 0.35 is above what a random draw reaches -- the
# best of the first forty proposals in six trial runs was 0.30 -- and well below
# what the search reaches within five rounds, so it costs nothing but the first
# hour and buys a board where every card beat something real.
MINIMUM_FITNESS = 0.35

# The evidence floor on the sealed window, identical to the screen's.
MINIMUM_SEALED_TRADES = hs.MINIMUM_SEALED_TRADES

# Round trips a year the research era must show before a genome is a candidate.
#
# **Derived from the sealed window's LENGTH, never from what it contains.** 2026
# is about 0.62 of a year so far, and a verdict there rests on at least
# `MINIMUM_SEALED_TRADES`; a rule trading at 24 a year clears that, and one
# trading at ten does not. Nothing about 2026's returns enters this -- only how
# long it is, which was known on the day it was sealed.
#
# It is here because the first live run of the arena found a genome scoring
# 0.566 -- comfortably past the champion, past the floor, enduring the whole era
# -- that took EIGHTY-FIVE trades in eight years and would have taken none at all
# in the sealed window. It could never be promoted, so the search would have run
# for three days and published nothing, which is the failure this file exists to
# end. `launch.measure` already records `leanest_year_trades` on the same
# reasoning: a rule that skips whole years cannot be evaluated in a seven-month
# window, and that is knowable from training alone.
#
# DERIVED, not written down, so the two constants cannot drift apart. The first
# version of this said 24.0 next to a comment claiming it implied fifteen sealed
# trades; 24 x 0.62 is 14.88, and the test that asserts the identity caught it.
# `SEALED_YEARS` is deliberately today's figure rather than a live calculation:
# it only grows, so a floor fixed at the shortest the window has ever been is the
# conservative reading, and a threshold that moves under a running search is a
# threshold nothing can be compared against.
SEALED_YEARS = 0.62
TRADES_PER_YEAR_FLOOR = MINIMUM_SEALED_TRADES / SEALED_YEARS

# Bars per trading day at this resolution, for turning a hold in days into the
# real engine's hold in bars.
BARS_PER_DAY = hs.BARS_PER_DAY


# --------------------------------------------------------------------------- #
# The genome
# --------------------------------------------------------------------------- #

# Every axis the arena may vary, and the values it may take.
#
# Discrete rather than continuous, because the surrogate is a tree ensemble and
# because a grid is what the ledger can compare across rounds. The signal axes
# match `hypothesis_scan`'s so a row from either search means the same thing.
AXES: dict[str, tuple] = {
    "hour": tuple(range(24)),
    "threshold": (0.005, 0.0075, 0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.05),
    "hold_days": (1, 2, 3, 4, 5, 7, 10, 14),
    "trend_days": (5, 10, 20, 30, 45, 60, 90, 120),
    "stop": (0.05, 0.08, 0.12, 0.20, None),
    "stake": (0.06, 0.08, 0.12, 0.16, 0.20, 0.25, 1.0 / hs.SLOTS),
    "target_vol": (None, 0.004, 0.006, 0.009, 0.013),
}


@dataclass(frozen=True)
class Genome:
    """One complete system: when to buy, how long to hold, and how much to risk."""

    hour: int
    threshold: float
    hold_days: int
    trend_days: int
    stop: float | None
    stake: float
    target_vol: float | None

    @property
    def signal(self) -> tuple:
        """The part that decides WHICH trades happen.

        Separated because building the trade book is the expensive step and
        depends on nothing else -- so every genome sharing a signal shares a
        book, and the six money-management variants around it are nearly free.
        """
        return (self.hour, self.threshold, self.hold_days, self.trend_days)

    def features(self) -> list[float]:
        """The vector the surrogate sees.

        `None` is split into a value and a flag rather than encoded as a
        sentinel number. "No stop at all" is not "a stop at zero per cent", and
        a tree given -1.0 for it would happily interpolate between them.
        """
        return [
            float(self.hour),
            float(self.threshold),
            float(self.hold_days),
            float(self.trend_days),
            float(self.stop or 0.0),
            1.0 if self.stop is not None else 0.0,
            float(self.stake),
            float(self.target_vol or 0.0),
            1.0 if self.target_vol is not None else 0.0,
        ]

    def document(self) -> dict[str, Any]:
        return {
            "hour": self.hour,
            "threshold": round(self.threshold, 5),
            "hold_days": self.hold_days,
            "trend_days": self.trend_days,
            "stop": self.stop,
            "stake": round(self.stake, 4),
            "target_vol": self.target_vol,
        }

    @classmethod
    def read(cls, document: dict[str, Any]) -> "Genome":
        """Rebuild a genome from an archive row, snapped back onto the grid.

        Snapped because the row is rounded on the way out -- a stake of one
        third is written as 0.3333 -- and because a 72-hour run outlives the
        code that started it: an archive written under a different `AXES` must
        still produce a breedable parent rather than a crash. Nearest neighbour
        is the only sane reading of an off-grid value, and it is silent by
        design; the alternatives are dropping history or refusing to start.
        """
        return cls(
            hour=_nearest(AXES["hour"], int(document["hour"])),
            threshold=_nearest(AXES["threshold"], float(document["threshold"])),
            hold_days=_nearest(AXES["hold_days"], int(document["hold_days"])),
            trend_days=_nearest(AXES["trend_days"], int(document["trend_days"])),
            stop=_nearest(AXES["stop"], document.get("stop")),
            stake=_nearest(AXES["stake"], float(document["stake"])),
            target_vol=_nearest(AXES["target_vol"], document.get("target_vol")),
        )


def _nearest(values: tuple, current: Any) -> Any:
    """The value on this axis closest to `current`.

    `None` is a value here, not a missing one -- "no stop at all" and "a 5%
    stop" are different systems -- so it matches only itself, and a numeric
    value never snaps to it.
    """
    if current is None:
        return None if None in values else values[0]
    numeric = [value for value in values if value is not None]
    if not numeric:
        return values[0]
    return min(numeric, key=lambda value: abs(float(value) - float(current)))


def _index(values: tuple, current: Any) -> int:
    """Where `current` sits on this axis, snapping if it is off-grid."""
    try:
        return values.index(current)
    except ValueError:
        return values.index(_nearest(values, current))


def consistency(folds: list[float | None]) -> float:
    """The share of JUDGEABLE folds in which this genome scored at all.

    `None` is a fold that held too few trades to judge, and it is excluded from
    both sides of the fraction rather than counted as a failure. Ten trades
    cannot establish that a two-year stretch worked, and they cannot establish
    that it did not either; counting them against the genome turns absence of
    evidence into evidence of absence and makes every selective system score
    zero for the crime of being selective.

    Fewer than two judgeable folds is not a consistency claim at all -- one fold
    is the whole-era figure again, wearing a second name and holding a second
    veto -- so it returns zero rather than a flattering 1.0.
    """
    judgeable = [value for value in folds if value is not None]
    if len(judgeable) < 2:
        return 0.0
    return sum(1 for value in judgeable if value > 0.0) / len(judgeable)


def random_genome(rng: random.Random) -> Genome:
    return Genome(**{name: rng.choice(values) for name, values in AXES.items()})


def mutate(genome: Genome, rng: random.Random, rate: float = 0.3) -> Genome:
    """Move a few axes to a NEIGHBOURING value, not to a random one.

    A mutation that teleports is a random restart wearing a genetic name: it
    destroys whatever made the parent worth keeping, and the population never
    refines anything. Stepping one place along the axis is what makes an elite
    pool converge on a ridge instead of resampling the space.
    """
    fields = dict(genome.__dict__)
    for name, values in AXES.items():
        if rng.random() >= rate:
            continue
        at = _index(values, fields[name])
        step = rng.choice((-1, 1))
        fields[name] = values[max(0, min(len(values) - 1, at + step))]
    return Genome(**fields)


def cross(one: Genome, other: Genome, rng: random.Random) -> Genome:
    """Take each axis from one parent or the other, uniformly."""
    return Genome(
        **{
            name: (getattr(one, name) if rng.random() < 0.5 else getattr(other, name))
            for name in AXES
        }
    )


# --------------------------------------------------------------------------- #
# What a genome is worth
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Verdict:
    """One genome, measured. Everything the archive keeps about it."""

    genome: Genome
    fitness: float
    whole: dict[str, Any]
    consistent: float
    frequent: float
    trades_per_year: float
    # Per-fold scores, with `None` where the fold held too few trades to judge.
    folds: list[float | None]
    taken: int
    sealed_trades: int
    endures: bool

    def document(self) -> dict[str, Any]:
        return {
            **self.genome.document(),
            "fitness": round(self.fitness, 5),
            "consistent": round(self.consistent, 3),
            "frequent": round(self.frequent, 3),
            "trades_per_year": self.trades_per_year,
            "folds": [None if v is None else round(v, 4) for v in self.folds],
            "taken": self.taken,
            # A count, never a return. See the module docstring: this is how much
            # evidence 2026 holds, which is a different kind of statement from
            # what the evidence says, and only the first may reach a decision.
            "sealed_trades": self.sealed_trades,
            "endures": self.endures,
            "quality": self.whole,
        }


class Arena:
    """The population, the archive, the surrogate and the champion."""

    def __init__(self, tapes_train, tapes_forward, seed: int = 0) -> None:
        self.train = tapes_train
        self.forward = tapes_forward
        self.rng = random.Random(seed)
        # Trade books keyed by signal genome. Building one walks twelve tapes in
        # Python and is the expensive step by an order of magnitude; the money
        # axes around it are array arithmetic.
        self._books: dict[tuple, Any] = {}
        self._sealed: dict[tuple, int] = {}
        self.archive: list[dict[str, Any]] = []
        self.model = None
        self._bounds = self._fold_bounds()
        # How long the research era is, for turning a trade count into a rate.
        self._years = (
            (self._bounds[-1][1] - self._bounds[0][0]) / np.timedelta64(1, "D") / 365.25
            if self._bounds
            else 0.0
        )

    # -- the tape ----------------------------------------------------------- #

    def _fold_bounds(self) -> list[tuple[np.datetime64, np.datetime64]]:
        """Four contiguous windows spanning the research era, by TIME.

        By time rather than by trade count, deliberately. Equal-count folds would
        put a quiet stretch and a frantic one in the same box and call them
        comparable; the question being asked is whether the system worked in
        every PERIOD, so the periods are what must be equal.
        """
        stamps = [tape.stamp for tape in self.train.values() if len(tape.stamp)]
        if not stamps:
            return []
        first = min(column[0] for column in stamps)
        last = max(column[-1] for column in stamps)
        span = (last - first) / FOLDS
        return [(first + span * i, first + span * (i + 1)) for i in range(FOLDS)]

    def _book(self, genome: Genome):
        """This genome's research-era trades, built once per signal."""
        key = genome.signal
        if key not in self._books:
            if len(self._books) > 600:
                # Bounded, because a 72-hour run visits tens of thousands of
                # signals and every book holds six float arrays. Oldest first:
                # the population moves, and the signals it has left behind are
                # the ones it will not ask for again.
                for stale in list(self._books)[:200]:
                    self._books.pop(stale, None)
            self._books[key] = hs.trades(self.train, hs.Candidate(*key))
        return self._books[key]

    def _sealed_count(self, genome: Genome) -> int:
        """How many trades 2026 would have held. A count, never a return."""
        key = genome.signal
        if key not in self._sealed:
            if len(self._sealed) > 4000:
                self._sealed.clear()
            book = hs.trades(self.forward, hs.Candidate(*key))
            gated = book.where(book.regime <= hs.MARKET_GATE)
            walked = hs.walk(
                gated,
                stop=genome.stop,
                stake=genome.stake,
                target_vol=genome.target_vol,
            )
            self._sealed[key] = walked.taken
        return self._sealed[key]

    # -- the objective ------------------------------------------------------ #

    def measure(self, genome: Genome) -> Verdict | None:
        """Score one genome on the research era. Returns None if it cannot be.

        The gate is applied and never searched, exactly as in `hypothesis_scan`:
        it is a structural prior about when a long-only book should be in the
        market at all, it cannot be fitted honestly on a research era that is
        almost entirely a rising market, and the one falling year available is
        the sealed one, which never chooses parameters.
        """
        book = self._book(genome)
        gated = book.where(book.regime <= hs.MARKET_GATE)
        if len(gated.entry) < hs.MINIMUM_TRADES:
            return None
        walked = hs.walk(
            gated, stop=genome.stop, stake=genome.stake, target_vol=genome.target_vol
        )
        whole = walked.judged()

        # Each fold walked as its own book, from its own opening capital. Slicing
        # the whole-era curve instead would hand every late fold the compounding
        # of the early ones, and a fold that merely held on to a fortune made
        # three years earlier would score as a fold that worked.
        # A fold with too few trades in it is EXCLUDED, never failed.
        #
        # `None` rather than 0.0, and the distinction is the whole clause. Ten
        # trades cannot establish that a two-year stretch worked, and they cannot
        # establish that it did not either -- so counting them as a failure makes
        # absence of evidence into evidence of absence, and every low-frequency
        # genome scores zero for the crime of being selective. The incumbent did
        # exactly that on the first run of this file: 44 trades over eight years,
        # four folds all marked failed, fitness 0.00, and the floor it was meant
        # to set was no floor at all.
        folds: list[float | None] = []
        for start, end in self._bounds:
            window = gated.where((gated.entry >= start) & (gated.entry < end))
            if len(window.entry) < 10:
                folds.append(None)
                continue
            folds.append(
                hs.walk(
                    window,
                    stop=genome.stop,
                    stake=genome.stake,
                    target_vol=genome.target_vol,
                )
                .judged()
                .score
            )
        consistent = consistency(folds)
        # The eighth term: does this rule trade often enough to be JUDGED in a
        # seven-month window. Measured on the research era, against a floor
        # derived from how long the sealed window is -- see
        # `TRADES_PER_YEAR_FLOOR`. Nothing about what 2026 contains is consulted.
        rate = walked.taken / self._years if self._years > 0 else 0.0
        frequent = max(0.0, min(1.0, rate / TRADES_PER_YEAR_FLOOR))

        # The seventh and eighth terms sit in the same geometric mean as the
        # other six, with the same veto. Not multipliers bolted on afterwards: a
        # multiplier would be worth more or less than growth depending on where
        # the score happened to sit, and the whole design of this objective is
        # that the properties are peers.
        terms = list(whole.terms().values()) + [consistent, frequent]
        if whole.score <= 0.0 or any(value <= 0.0 for value in terms):
            fitness = 0.0
        else:
            fitness = math.exp(sum(math.log(v) for v in terms) / len(terms))

        return Verdict(
            genome=genome,
            fitness=fitness,
            whole=whole.document(),
            consistent=consistent,
            frequent=frequent,
            trades_per_year=round(rate, 2),
            folds=folds,
            taken=walked.taken,
            sealed_trades=self._sealed_count(genome),
            endures=walked.endures,
        )

    def best_of_signal(self, signal: dict[str, Any]) -> Verdict | None:
        """The best this signal can be made to do, over every money variant.

        175 walks -- five stops, seven stakes, five volatility targets -- against
        one trade book that is built once. Exhaustive rather than the two-pass
        coordinate descent `hypothesis_scan.money` uses, because that exists to
        make seven thousand candidates a cycle affordable and this is called once
        at start-up.
        """
        best: Verdict | None = None
        for stop in AXES["stop"]:
            for stake in AXES["stake"]:
                for target in AXES["target_vol"]:
                    verdict = self.measure(
                        Genome(**signal, stop=stop, stake=stake, target_vol=target)
                    )
                    if verdict is None:
                        continue
                    if best is None or verdict.fitness > best.fitness:
                        best = verdict
        return best

    # -- the surrogate ------------------------------------------------------ #

    def fit_surrogate(self) -> str | None:
        """Fit the model that decides which genomes are worth measuring.

        Returns a one-line description, or None if there is not enough archive
        yet -- in which case the round proposes at random, which is the correct
        behaviour and not a degraded one. A model fitted on forty points would
        confidently rank fifteen hundred, and the search would spend its first
        hours exploring whatever those forty happened to suggest.
        """
        if len(self.archive) < 120:
            self.model = None
            return None
        try:
            from sklearn.ensemble import HistGradientBoostingRegressor
        except ImportError:
            self.model = None
            return "scikit-learn not installed; proposing at random"
        x = np.array([row["features"] for row in self.archive], dtype=float)
        y = np.array([row["fitness"] for row in self.archive], dtype=float)
        model = HistGradientBoostingRegressor(
            max_depth=6, learning_rate=0.08, max_iter=250, l2_regularization=1.0
        )
        model.fit(x, y)
        self.model = model
        return f"surrogate fitted on {len(y):,} evaluations"

    def propose(self, elites: list[Genome]) -> list[tuple[Genome, float | None]]:
        """The genomes this round will measure, and what the model expected.

        `IMMIGRANTS` of them are drawn at random and kept WHATEVER the model
        says about them. A surrogate trained only on what the surrogate chose
        will agree with itself for ever, and its archive stops being a fair
        sample of the space it claims to model -- so the honest measurement of
        whether it is improving would go with it.
        """
        seen: set[Genome] = set()
        pool: list[Genome] = []
        while len(pool) < PROPOSALS:
            if elites and self.rng.random() < 0.75:
                parent = self.rng.choice(elites)
                if len(elites) > 1 and self.rng.random() < 0.4:
                    child = cross(parent, self.rng.choice(elites), self.rng)
                else:
                    child = mutate(parent, self.rng)
            else:
                child = random_genome(self.rng)
            if child in seen:
                continue
            seen.add(child)
            pool.append(child)

        immigrants = [random_genome(self.rng) for _ in range(IMMIGRANTS)]
        if self.model is None:
            chosen = pool[: MEASURED - IMMIGRANTS]
            return [(g, None) for g in chosen + immigrants]

        x = np.array([g.features() for g in pool], dtype=float)
        predicted = self.model.predict(x)
        order = np.argsort(-predicted)[: MEASURED - IMMIGRANTS]
        chosen = [(pool[int(i)], float(predicted[int(i)])) for i in order]
        blind = self.model.predict(
            np.array([g.features() for g in immigrants], dtype=float)
        )
        return chosen + [(g, float(p)) for g, p in zip(immigrants, blind, strict=False)]


def spearman(predicted: list[float], actual: list[float]) -> float | None:
    """Rank correlation, as the honest report card on the surrogate.

    Rank rather than value because nothing downstream uses the model's numbers:
    it is asked only to ORDER fifteen hundred genomes so the top forty are worth
    measuring, and a model that is badly calibrated but correctly ordered does
    that job perfectly.
    """
    pairs = [(p, a) for p, a in zip(predicted, actual, strict=False) if p is not None]
    if len(pairs) < 8:
        return None

    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        for position, index in enumerate(order):
            out[index] = float(position)
        return out

    left = ranks([p for p, _ in pairs])
    right = ranks([a for _, a in pairs])
    n = len(pairs)
    mean = (n - 1) / 2.0
    num = sum((a - mean) * (b - mean) for a, b in zip(left, right, strict=False))
    den = math.sqrt(
        sum((a - mean) ** 2 for a in left) * sum((b - mean) ** 2 for b in right)
    )
    return num / den if den > 0 else None


# --------------------------------------------------------------------------- #
# Promotion: the only thing here that costs real time
# --------------------------------------------------------------------------- #


def brain_parameters(genome: Genome) -> dict[str, Any]:
    """This genome as the real engine's parameters.

    **The stake mapping is approximate and says so.** The screen commits a
    FRACTION OF EQUITY per position; the engine sizes from `risk_per_trade`
    against an ATR stop, and with `stop_atr=60` every position is pinned to the
    30% position cap -- measured, not assumed: `risk_per_trade` 0.05, 0.025 and
    0.0125 produced full, half and quarter positions. So the map is stake times
    a sixth, bounded. The screen decides what deserves a backtest; the backtest
    decides what is true, and where they disagree the backtest is right.
    """
    return {
        "entry_rule": "itsm",
        "itsm_hour": genome.hour,
        "itsm_threshold": round(genome.threshold, 5),
        "trend_ma_days": genome.trend_days,
        "maximum_holding_bars": genome.hold_days * BARS_PER_DAY,
        # No ATR stop. The screen's stop is a percentage of the entry price on
        # the lowest close and the engine's is a multiple of ATR; they are not
        # the same instrument, so pretending to carry one across would be worse
        # than carrying neither.
        "stop_atr": 60.0,
        "trail_atr": 0.0,
        "exit_end_of_day": False,
        "drawdown_basis": "initial",
        "market_gate_drawdown": hs.MARKET_GATE,
        "maximum_positions": hs.SLOTS,
        "risk_per_trade": round(min(0.05, max(0.005, genome.stake / 6.0)), 5),
    }


def promote(verdict: Verdict, label: str, log) -> bool:
    """Run and publish BOTH halves of this hypothesis. True if both succeeded.

    Both, always, and identical but for `trade_from`. A training run without its
    sealed twin cannot be paired by the monitor and is half an answer; the house
    rule exists because this laboratory published several of them.
    """
    flags: list[str] = []
    for key, value in brain_parameters(verdict.genome).items():
        flags += ["--set", f"{key}={value}"]

    environment = dict(os.environ)
    environment["PYTHONPATH"] = "backtester:trading-system:orchestrator-manager"
    for phase in ("training", "forward"):
        command = [
            str(ROOT / ".venv" / "bin" / "python"),
            str(ROOT / "orchestrator-manager" / "scripts" / "publish_intraday.py"),
            "--phase",
            phase,
            "--brain",
            "intraday-momentum",
            "--label",
            label,
            "--symbols",
            ",".join(hs.SYMBOLS),
            *flags,
        ]
        log(f"  {phase}: {' '.join(command[-6:])}")
        finished = subprocess.run(
            command,
            cwd=str(ROOT),
            env=environment,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        for line in finished.stdout.strip().splitlines()[-6:]:
            log(f"    {line}")
        if finished.returncode != 0:
            log(f"  {phase} FAILED rc={finished.returncode}")
            for line in finished.stderr.strip().splitlines()[-8:]:
                log(f"    ! {line}")
            return False
    return True


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #


def read_champion() -> dict[str, Any] | None:
    if not CHAMPION.exists():
        return None
    try:
        return json.loads(CHAMPION.read_text())
    except (OSError, ValueError):
        return None


def _floor() -> float:
    """The reigning champion's screen fitness, or zero if there is none yet."""
    champion = read_champion()
    try:
        return float(champion["fitness"]) if champion else 0.0
    except (KeyError, TypeError, ValueError):
        return 0.0


def read_archive(limit: int = 60_000) -> list[dict[str, Any]]:
    """Everything measured in every previous run of this process.

    The archive IS the self-improvement. A restart that lost it would start the
    surrogate from nothing every six hours, and the supervisor restarts this
    process on purpose -- which is precisely the bug that made the previous
    search re-score cycle zero nine times in a row.
    """
    if not ARCHIVE.exists():
        return []
    rows: list[dict[str, Any]] = []
    with ARCHIVE.open() as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if "features" in row and "fitness" in row:
                rows.append(row)
    return rows[-limit:]


def promotions_today(ledger: Path) -> int:
    """How many pairs have already been published today.

    Read off the ledger rather than counted in a variable, for the same reason
    the cycle counter is: the supervisor restarts this process, and a cap held in
    memory is a cap that resets.
    """
    if not ledger.exists():
        return 0
    today = datetime.now(timezone.utc).date().isoformat()
    count = 0
    with ledger.open() as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if str(row.get("at", ""))[:10] == today:
                count += len(row.get("promoted", []))
    return count


def run_round(arena: Arena, index: int, log) -> dict[str, Any]:
    """One generation: fit, propose, measure, archive, promote if it earned it."""
    started = time.time()
    note = arena.fit_surrogate()
    if note:
        log(note)

    # Only genomes that SCORED may breed.
    #
    # Seven terms each holding a veto means about five sixths of the space scores
    # exactly zero, so a plain top-thirty is mostly a list of failures tied at the
    # bottom -- and mutating a failure produces a failure. The first run of this
    # file measured thirty-eight genomes in its second round and every one of
    # them scored zero, because round one's "elites" were twenty-five zeros and
    # five real candidates. Ties at zero carry no information about direction,
    # which is the only thing a parent is for.
    ranked = sorted(arena.archive, key=lambda row: -row["fitness"])
    scoring = [row for row in ranked if row["fitness"] > 0.0][:30]
    elites = [Genome.read(row) for row in scoring]
    proposed = arena.propose(elites)

    verdicts: list[Verdict] = []
    predicted: list[float | None] = []
    actual: list[float] = []
    rejected = 0
    for genome, guess in proposed:
        verdict = arena.measure(genome)
        if verdict is None:
            rejected += 1
            continue
        verdicts.append(verdict)
        predicted.append(guess)
        actual.append(verdict.fitness)
        arena.archive.append(
            {
                **verdict.genome.document(),
                "features": verdict.genome.features(),
                "fitness": verdict.fitness,
            }
        )

    with ARCHIVE.open("a") as handle:
        for verdict in verdicts:
            handle.write(
                json.dumps(
                    {
                        **verdict.genome.document(),
                        "features": verdict.genome.features(),
                        "fitness": round(verdict.fitness, 6),
                        "round": index,
                    }
                )
                + "\n"
            )

    verdicts.sort(key=lambda v: -v.fitness)
    # Two floors, and the higher wins. The champion's, because the board must
    # ratchet; and an absolute one, because the incumbent screens below it -- the
    # instrument is harsher than the engine and a champion that screens at 0.00
    # would let the arena publish its first lucky draw.
    floor = max(_floor(), MINIMUM_FITNESS)

    promoted: list[dict[str, Any]] = []
    allowance = DAILY_PROMOTIONS - promotions_today(LEDGER)
    for verdict in verdicts:
        if allowance <= 0:
            break
        if verdict.fitness <= floor * PROMOTION_MARGIN or verdict.fitness <= 0.0:
            break
        if not verdict.endures:
            continue
        # An evidence floor, not a performance one. A genome that would have taken
        # four trades in the sealed window cannot be compared with one that took
        # thirty, whatever either of them returned -- and what they returned is
        # not consulted here or anywhere else in this file.
        if verdict.sealed_trades < MINIMUM_SEALED_TRADES:
            continue
        label = (
            f"arena r{index} h{verdict.genome.hour} "
            f"{verdict.genome.threshold:.3%} {verdict.genome.hold_days}d"
        )
        log(f"promoting {label}: fitness {verdict.fitness:.4f} over floor {floor:.4f}")
        if promote(verdict, label, log):
            promoted.append({"label": label, **verdict.document()})
            floor = verdict.fitness
            allowance -= 1
            CHAMPION.write_text(
                json.dumps({"label": label, **verdict.document()}, indent=2)
            )
        else:
            log("  publication failed; champion unchanged")

    best = verdicts[0] if verdicts else None
    return {
        "round": index,
        "at": datetime.now(timezone.utc).isoformat(),
        "seconds": round(time.time() - started, 1),
        "measured": len(verdicts),
        # Genomes whose gated book was too small to be a strategy. Reported
        # because a round that measured six of forty is a round whose ranking
        # rests on six, and a reader who does not know that cannot tell.
        "rejected": rejected,
        "archive": len(arena.archive),
        "surrogate": arena.model is not None,
        # The report card. Spearman between what the model predicted for this
        # round's genomes and what they scored -- computed before the truth was
        # known, so it is out-of-sample in time. This rising across rounds IS the
        # claim that the search is getting more efficient, and it is falsifiable.
        "rank_correlation": (
            None if (rho := spearman(predicted, actual)) is None else round(rho, 4)
        ),
        "best_fitness": round(best.fitness, 5) if best else 0.0,
        "best": best.document() if best else None,
        "champion_fitness": round(floor, 5),
        "promoted": promoted,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help="0 runs until the stop file appears",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--no-promote",
        action="store_true",
        help="search and archive, but publish nothing. For a smoke test.",
    )
    args = parser.parse_args(argv)

    ARENA.mkdir(parents=True, exist_ok=True)

    def log(message: str) -> None:
        print(f"{datetime.now():%H:%M:%S} {message}", flush=True)

    log("loading tapes ...")
    train = {s: t for s in hs.SYMBOLS if (t := hs.load("research", s)) is not None}
    forward = {
        s: t for s in hs.SYMBOLS if (t := hs.load("forward", s, warm=True)) is not None
    }
    log(f"training {len(train)} symbols, sealed {len(forward)} symbols")

    arena = Arena(train, forward, seed=args.seed)
    arena.archive = read_archive()
    log(f"archive: {len(arena.archive):,} previous evaluations")

    # The bar to clear, measured on this instrument, before anything is proposed.
    if not CHAMPION.exists():
        seed = arena.best_of_signal(INCUMBENT_SIGNAL)
        if seed is None:
            log("WARNING: the incumbent cannot be screened; the floor is the minimum")
        else:
            CHAMPION.write_text(
                json.dumps(
                    {"label": "incumbent gate-40 thr-2.5pct", **seed.document()},
                    indent=2,
                )
            )
            log(
                f"floor: the incumbent's best screen fitness is {seed.fitness:.4f} "
                f"at stake {seed.genome.stake:.3f} stop {seed.genome.stop} "
                f"({seed.taken} trades, folds {seed.folds})"
            )
    log(
        f"a challenger must clear {max(_floor(), MINIMUM_FITNESS) * PROMOTION_MARGIN:.4f}"
    )
    if args.no_promote:
        global DAILY_PROMOTIONS
        DAILY_PROMOTIONS = 0

    index = 0
    while True:
        if STOP_FILE.exists():
            log(f"stop file present: {STOP_FILE}")
            return 0
        report = run_round(arena, index, log)
        with LEDGER.open("a") as handle:
            handle.write(json.dumps(report) + "\n")
        rho = report["rank_correlation"]
        log(
            f"round {index}: {report['measured']} measured "
            f"({report['rejected']} too thin), best {report['best_fitness']:.4f}, "
            f"champion {report['champion_fitness']:.4f}, "
            f"archive {report['archive']:,}, "
            f"surrogate rho {'--' if rho is None else f'{rho:+.3f}'}, "
            f"{len(report['promoted'])} promoted, {report['seconds']}s"
        )
        index += 1
        if args.rounds and index >= args.rounds:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
