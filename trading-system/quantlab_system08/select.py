"""Selection: choose the configuration on RESEARCH data, then read 2026 exactly once.

THE DISCIPLINE, AND WHY IT IS NOT "DO NOT TUNE"

A system with no fitted choices is not a finished system; it is a first sketch. Tuning is
part of building. What destroys a laboratory is not tuning - it is tuning against the thing
you later report as your out-of-sample result, and then reporting the winner's statistics as
though it were the only candidate ever tried.

So this module enforces three rules, and they are the whole difference between development
and self-deception:

  1. SELECTION HAPPENS ON RESEARCH DATA ONLY. The sealed year is never an input to the
     choice. The catalogue makes this structural rather than a promise: `research()` cannot
     return a 2026 bar.

  2. SELECTION HAPPENS ON HELD-OUT YEARS, not on the whole record. A configuration is
     scored on research years it did not get to see during fitting, because a score
     computed on everything is a score computed on the thing being chosen. Here the split
     is by time: fit years are the earlier ones, the validation years are the later ones,
     and the config is ranked on validation only.

  3. EVERY CONFIGURATION TRIED IS COUNTED. `trials` is the size of the grid, and it is what
     the deflated Sharpe is corrected against. Trying 54 configurations and reporting the
     winner's raw Sharpe is the specific arithmetic that produced six systems here which
     were positive in research and negative in the same forward year.

WHAT THE SCORE REWARDS

The operator's mandate is a minimum +30% per calendar year, EVERY year, with drawdown as an
objective to minimise. So the selection criterion is not total return - a single 2021 can
carry a decade - but consistency first and depth of hole second. Ranking on total return is
how this laboratory previously adopted systems that made all their money in one year and
then died.
"""

from __future__ import annotations

import itertools
import statistics
from dataclasses import dataclass, replace

from .book import BookResult
from .system import Config, build

# The grid. Deliberately small and deliberately coarse: every point in it makes every
# result statistically weaker, because the deflated Sharpe is corrected against the count.
# These are ranges the literature points at, not a fine sweep around a lucky value.
GRID = {
    "window": (40, 60, 90),        # loading estimation, in days
    "lookback": (14, 28, 56),      # residual momentum formation window
    "hold": (7, 14, 28),           # rebalance cadence; DS3's factor is two-week
    "side_fraction": (1.0 / 3.0, 0.5),
}

# Research years used for validation. Everything earlier is what a configuration is
# allowed to be shaped by; these are the years it is RANKED on. Two years is thin, and
# that thinness is itself a reason to distrust a narrow winner.
VALIDATION_YEARS = (2024, 2025)


@dataclass(frozen=True)
class Scored:
    config: Config
    fit_years: dict[int, float]
    validation_years: dict[int, float]
    score: float
    validation_return: float
    validation_drawdown: float

    @property
    def label(self) -> str:
        c = self.config
        return (f"w{c.window}/lb{c.lookback}/h{c.hold}/"
                f"s{c.side_fraction:.2f}")


def configs() -> list[Config]:
    keys = sorted(GRID)
    out = []
    for values in itertools.product(*(GRID[k] for k in keys)):
        out.append(replace(Config(), **dict(zip(keys, values))))
    return out


def _drawdown(result: BookResult, years: tuple[int, ...]) -> float:
    days = [d for d in result.days if int(d.day[:4]) in years]
    if not days:
        return 1.0
    peak, worst = days[0].equity, 0.0
    for d in days:
        peak = max(peak, d.equity)
        if peak > 0:
            worst = max(worst, (peak - d.equity) / peak)
    return worst


def score_config(result: BookResult,
                 validation: tuple[int, ...] = VALIDATION_YEARS) -> Scored | None:
    """Rank on the held-out years, on consistency first and hole depth second.

    Returns None when a configuration produced no validation years at all, which is a
    refusal rather than a zero: a config that cannot be evaluated has not earned a place
    in the ranking simply by being unmeasurable.
    """
    by_year = result.by_year()
    val = {y: v for y, v in by_year.items() if y in validation}
    fit = {y: v for y, v in by_year.items() if y not in validation}
    if not val:
        return None

    positive = sum(1 for v in val.values() if v > 0)
    median = statistics.median(val.values())
    dd = _drawdown(result, validation)

    # Consistency dominates: every positive validation year is worth more than any amount
    # of return in one of them. Then the median year, then a penalty for the hole it dug.
    score = positive * 1.0 + median - dd
    compounded = 1.0
    for v in val.values():
        compounded *= (1.0 + v)
    return Scored(Config(), fit, val, score, compounded - 1.0, dd)


def sweep(bars: dict, grid_configs: list[Config] | None = None,
          validation: tuple[int, ...] = VALIDATION_YEARS,
          on_progress=None) -> list[Scored]:
    """Run every configuration on research bars and rank them on the held-out years.

    `bars` must be research bars. Passing sealed bars here would make the selection read
    the future, so the caller loads them with `cat.research()` and nothing in this module
    reaches for the catalogue itself.
    """
    cfgs = grid_configs or configs()
    scored: list[Scored] = []
    for i, cfg in enumerate(cfgs, start=1):
        try:
            run = build(bars, cfg, trials=len(cfgs))
        except Exception as exc:          # a config that cannot run is not a candidate
            if on_progress:
                on_progress(i, len(cfgs), cfg, None, str(exc))
            continue
        s = score_config(run.result, validation)
        if s is None:
            if on_progress:
                on_progress(i, len(cfgs), cfg, None, "no validation years")
            continue
        s = replace(s, config=cfg)
        scored.append(s)
        if on_progress:
            on_progress(i, len(cfgs), cfg, s, "")
    return sorted(scored, key=lambda s: s.score, reverse=True)
