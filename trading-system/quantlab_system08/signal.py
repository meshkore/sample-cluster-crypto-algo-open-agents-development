"""The signal: cross-sectional momentum OF THE RESIDUAL, long and short.

This module turns residual series into target weights. It holds no state, touches no
ledger and knows nothing about execution, so every decision in it can be tested against a
hand-built example.

WHAT THE EVIDENCE FIXED, AND WHAT IT LEFT TO US

Four constraints came out of the design's reading fronts, and each is forced by a
citation rather than chosen. They are enforced here rather than documented elsewhere and
hoped for:

  LARGE CAPS ONLY. Zaremba and co-authors (IRFA 2024) put the crypto anomalies through
  economic constraints and find size, volume and distress profitability comes SOLELY from
  the 30-70% smallest coins, and short-term reversal from low-volume, low-liquidity
  names. Momentum is the one that prevails in the LARGER cryptocurrencies. Our universe
  snapshot is already screened at a USD 10M daily turnover floor, so this constraint is
  satisfied upstream - `require_screened_universe()` asserts it rather than assuming it,
  because the day someone widens the universe is the day this design stops being the
  design that was argued.

  THE SHORT SIDE IS MANDATORY. The same paper: momentum "extracts alphas largely from
  SHORT positions". This is why the book is long/short and not long-tilted, and it is the
  finding that makes the operator lifting long-only on 2026-09-08 load-bearing rather
  than convenient. Six long-only systems in this laboratory could not have captured this
  even had they found it.

  TURNOVER IS THE ENEMY. The same paper reports substantial trading costs; Li and Zhu's
  surviving momentum factor is a TWO-WEEK one. So the default holding period is two weeks
  and the default lookback is measured in weeks, not days. The horizon is pointed at by
  evidence rather than swept as a parameter, which matters because sweeping it is exactly
  how this laboratory previously manufactured six systems that died together.

  EXPECT DECAY. Later-period alphas run 9-76% lower. Nothing here is built to be defended.

WHAT IS DELIBERATELY SIMPLE

Rank, split, weight by inverse residual volatility. No optimiser, no covariance
inversion, no blending. Every additional degree of freedom multiplies the number of
configurations tried, and the number of configurations tried is precisely what the
probability-of-backtest-overfitting literature says converts a real edge into a selected
one. The design's own history is six systems that all died in the same forward year.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Two weeks. Li & Zhu's surviving crypto momentum factor is a two-week one, so the
# holding period matches the horizon the evidence actually validated.
DEFAULT_HOLD_DAYS = 14
# The formation window over which residual momentum is accumulated.
DEFAULT_LOOKBACK_DAYS = 28
# Days skipped between the end of the formation window and the position. Classical
# momentum skips the most recent period to avoid contaminating the signal with
# short-term reversal, which the crypto literature reports separately and which lives in
# exactly the low-liquidity names we have excluded. One day, not one month: our horizon
# is weeks, and skipping a month of a four-week window would leave nothing.
DEFAULT_SKIP_DAYS = 1
# Fraction of the cross-section taken on each side. A third each way keeps both legs
# populated on a universe of this size; finer slicing on thirteen names is noise
# dressed as selectivity.
DEFAULT_SIDE_FRACTION = 1.0 / 3.0
# Gross exposure cap, summed over both legs. Leverage is permitted but MINIMAL, and the
# operator's reason is execution risk rather than volatility: "the moment you send the
# order there will be a thousand orders ahead of yours."
DEFAULT_GROSS_CAP = 1.0
# A leg needs at least this many names before it is taken at all. One name is not a
# cross-section, and a one-name leg is an idiosyncratic bet wearing a portfolio's label.
MIN_NAMES_PER_SIDE = 2


class UniverseNotScreened(Exception):
    """Raised when the universe was not screened the way the design was argued for."""


def require_screened_universe(meta: dict) -> None:
    """Assert the universe still matches the capacity argument the design rests on.

    The design rejected size and reversal as signals ON CAPACITY GROUNDS - they live
    below our turnover floor. That rejection is only valid while the floor is actually
    applied. If someone widens the universe to chase names, the design silently becomes
    a different design, so this raises instead.
    """
    floor = meta.get("min_turnover")
    if not floor or float(floor) < 10_000_000.0:
        raise UniverseNotScreened(
            f"universe min_turnover is {floor!r}; the design requires a USD 10M daily "
            f"turnover floor, because it rejected size and reversal as signals on the "
            f"grounds that they live below it. Widening the universe invalidates that "
            f"rejection, so re-argue the design before changing this.")


@dataclass(frozen=True)
class Target:
    """One desired position. `weight` is SIGNED: negative is short."""

    symbol: str
    weight: float
    score: float
    resid_vol: float

    @property
    def is_short(self) -> bool:
        return self.weight < 0


def residual_momentum(eps: dict[str, float], day: str,
                      lookback: int = DEFAULT_LOOKBACK_DAYS,
                      skip: int = DEFAULT_SKIP_DAYS) -> float | None:
    """Cumulative residual return over the formation window ending `skip` days before
    `day`. Returns None when the window is not fully covered.

    Compounding rather than summing: the residual is a return series, and a book that
    holds it earns the compounded path. Requiring FULL coverage is deliberate - a name
    with half a window is not a weaker signal, it is a different measurement, and
    letting it rank against full-window names is how a universe change turns into a
    performance change nobody can attribute.
    """
    days = sorted(d for d in eps if d < day)
    if skip:
        days = days[:-skip] if len(days) > skip else []
    if len(days) < lookback:
        return None
    window = days[-lookback:]
    total = 1.0
    for d in window:
        total *= (1.0 + eps[d])
    return total - 1.0


def rank_and_size(scores: dict[str, float], vols: dict[str, float],
                  side_fraction: float = DEFAULT_SIDE_FRACTION,
                  gross_cap: float = DEFAULT_GROSS_CAP,
                  min_names: int = MIN_NAMES_PER_SIDE) -> list[Target]:
    """Rank the cross-section, take both extremes, size by inverse residual volatility.

    Returns an empty list - meaning STAND ASIDE - whenever either leg would be too thin.
    Standing aside is a position: the operator's constraint is that leverage is minimal
    because of execution risk, and a book that must always be invested is a book that
    trades its way into the worst tape it can find.

    The two legs are scaled to be equal in gross terms. This is what makes the book a
    RELATIVE bet on the cross-section rather than a directional one wearing a hedge: if
    the long leg were larger simply because its names happened to be less volatile, the
    residual book would carry a net position it never intended.
    """
    usable = {s: v for s, v in scores.items()
              if v is not None and np.isfinite(v) and vols.get(s, 0.0) > 0}
    if len(usable) < 2 * min_names:
        return []

    ordered = sorted(usable, key=lambda s: usable[s], reverse=True)
    n_side = max(min_names, int(len(ordered) * side_fraction))
    if 2 * n_side > len(ordered):
        n_side = len(ordered) // 2
    if n_side < min_names:
        return []

    longs, shorts = ordered[:n_side], ordered[-n_side:]

    def raw(names):
        # Inverse residual volatility: equalise the risk each name contributes to the
        # residual book, which is the thing this design intends to own.
        return {s: 1.0 / vols[s] for s in names}

    lw, sw = raw(longs), raw(shorts)
    l_tot, s_tot = sum(lw.values()), sum(sw.values())
    if l_tot <= 0 or s_tot <= 0:
        return []

    # Half the gross to each side, so the legs are equal in gross terms by construction.
    half = gross_cap / 2.0
    out: list[Target] = []
    for s in longs:
        out.append(Target(s, half * lw[s] / l_tot, usable[s], vols[s]))
    for s in shorts:
        out.append(Target(s, -half * sw[s] / s_tot, usable[s], vols[s]))
    return out


DEFAULT_LIQUIDITY_WINDOW = 60


def liquid_names(turnover: dict[str, dict[str, float]], day: str, top_n: int,
                 window: int = DEFAULT_LIQUIDITY_WINDOW) -> set[str]:
    """The `top_n` names by median daily USD turnover over the window BEFORE `day`.

    WHY A SCREEN THAT MOVES

    The design's third reading front closed on a finding we then contradicted with our own
    code: cross-sectional momentum in crypto survives in the LARGE names, and the
    small-capitalisation and reversal variants were rejected on capacity. Cycle 3 then
    widened the cross-section from fourteen names to thirty-two, which is eighteen smaller
    names added to a book whose own research says the edge is not there. The research
    Sharpe rose and the sealed year went negative.

    So this is not a new idea, it is the design's existing conclusion finally expressed in
    code. The screen is causal and it MOVES: a name that was large in 2019 and small in
    2024 is in the book in 2019 and out of it in 2024, which is what a live book would
    have done. A fixed list of today's large names applied to 2019 is the purest form of
    survivorship, and it is the exact mistake this repository has made before.

    The MEDIAN rather than the mean, because a single listing-day volume spike is not
    liquidity. `day` itself is excluded: the window ends strictly before the bar it is
    used to trade.
    """
    if top_n <= 0:
        return set(turnover)
    ranked: list[tuple[float, str]] = []
    for sym, per_day in turnover.items():
        days = sorted(d for d in per_day if d < day)
        if len(days) < window:
            continue
        vals = sorted(per_day[d] for d in days[-window:])
        mid = len(vals) // 2
        med = vals[mid] if len(vals) % 2 else 0.5 * (vals[mid - 1] + vals[mid])
        if med > 0:
            ranked.append((med, sym))
    ranked.sort(reverse=True)
    return {sym for _, sym in ranked[:top_n]}


def seasoned_names(rets: dict[str, dict[str, float]], day: str,
                   min_history: int) -> set[str]:
    """Names with at least `min_history` days of tape strictly before `day`.

    WHY THIS IS A HYPOTHESIS TEST AND NOT A PARAMETER

    Widening the cross-section from fourteen names to thirty-two improved eight years of
    backtest and reversed the sign of the ninth. One explanation is that most of the added
    names listed in 2024 or later, so across the research years they contribute a few years
    each, while in the sealed year they are half the book. If that is what happened, the
    backtest is partly measuring a cross-section that did not exist at the time, and the
    forward read is the first honest look at the book we actually built.

    A minimum-seasoning rule is how that is tested: it makes the book's composition
    comparable across eras instead of letting it drift with the listing calendar. Counted
    strictly before `day`, like every other window in this system.
    """
    if min_history <= 0:
        return set(rets)
    return {sym for sym, series in rets.items()
            if sum(1 for d in series if d < day) >= min_history}


def targets_for_day(eps_by_symbol: dict[str, dict[str, float]],
                    vols_by_symbol: dict[str, float],
                    day: str,
                    lookback: int = DEFAULT_LOOKBACK_DAYS,
                    skip: int = DEFAULT_SKIP_DAYS,
                    side_fraction: float = DEFAULT_SIDE_FRACTION,
                    gross_cap: float = DEFAULT_GROSS_CAP) -> list[Target]:
    """The full signal for one rebalance day. Everything it reads predates `day`."""
    scores: dict[str, float] = {}
    for sym, eps in eps_by_symbol.items():
        score = residual_momentum(eps, day, lookback=lookback, skip=skip)
        if score is not None:
            scores[sym] = score
    return rank_and_size(scores, vols_by_symbol, side_fraction=side_fraction,
                         gross_cap=gross_cap)


def hedge_weight(targets: list[Target], betas: dict[str, float]) -> float:
    """The factor position that cancels the book's net loading: h = -sum(w * beta).

    A long/short book built on residuals is ALREADY close to factor-neutral, because the
    two legs' loadings largely offset. This returns what remains, and it is usually
    small. It is computed explicitly rather than assumed to be zero, because "it should
    net out" is the kind of assumption that turns a market-neutral book into a
    directional one in exactly the month the legs stop being symmetric.
    """
    return -sum(t.weight * betas.get(t.symbol, 0.0) for t in targets)
