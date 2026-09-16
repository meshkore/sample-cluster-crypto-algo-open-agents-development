"""The residual: what is left of an asset's return once the common factor is removed.

This is the load-bearing piece of System 08 and the one the whole design rests on, so it
is a separate module with no dependency on the book, the signal or the engine. It can be
read, tested and attacked on its own.

WHY A RESIDUAL AT ALL

Makarov and Schoar (JFE 2020) decompose signed volume across crypto venues and find the
COMMON component explains about 80% of bitcoin returns. Giller (arXiv 2412.04263) reaches
a compatible conclusion from the other direction on a retail universe. So a long crypto
book is mostly one position wearing many tickers, and whatever idiosyncratic information
it holds is buried under a factor nobody priced.

In equities, Blitz, Huij and Martens strip that factor out and run momentum on what
remains. The reported effect is not a small improvement: significantly higher
return-to-risk, greatly reduced crash risk, an almost doubled Sharpe ratio, the largest
reduction in maximum drawdown of the variants compared - and, rarely for a published
anomaly, it held up out of sample AFTER publication. The mechanism they give is specific:
conventional momentum accumulates DYNAMIC FACTOR EXPOSURE, because the winners become the
high-beta names, and it is that exposure rather than the idiosyncratic signal which
produces the crashes.

Li and Zhu carried the same construct to crypto: their DS3 model, selected by iterative
double-selection LASSO, keeps market, a two-week momentum factor, and RESIDUAL MOMENTUM -
in the same study that finds only 13 of 49 crypto anomalies still significant. The
procedure that kills the factor zoo is the one that keeps this.

THE TWO MISTAKES THIS MODULE REFUSES TO MAKE

  1. LOOKAHEAD. A loading estimated on a window that includes bar `t` explains bar `t`,
     and a book sized on it is reading its own answer. Every window here ends strictly
     BEFORE the bar whose residual it produces, and `loadings()` is written so that
     off-by-one is a test failure rather than a silent 30% of performance.

  2. LOG RETURNS IN A PORTFOLIO. The log return of a basket is not the mean of its
     constituents' log returns. Residuals are eventually aggregated across symbols, so
     everything here is SIMPLE returns. This is not pedantry: a previous measurement in
     this laboratory was wrong for exactly this reason.

WHAT IS A DECISION AND NOT A PARAMETER

The factor set. Li and Zhu's residual is defined against THEIR factors; ours is defined
against whatever we choose, and the choice changes what "idiosyncratic" means. The design
registered this as the first decision of implementation rather than letting a default
smuggle it in, so `FactorSet` is explicit and BTC-only is a named starting point, not an
assumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

# The estimation window for the factor loading, in trading days. A quarter: long enough
# that the covariance is not noise, short enough to track an exposure that genuinely
# drifts. Stated here once so that every consumer shares it and nobody re-tunes it
# privately.
DEFAULT_WINDOW = 60

# Minimum observations before a loading is produced at all. Below this the estimate is
# not merely noisy, it is meaningless, and returning it would let a book take a position
# on nothing.
MIN_OBS = 30

# The residual must be at least this fraction of the asset's own volatility, or the name
# is dropped.
#
# WHY THIS EXISTS. The book sizes by INVERSE residual volatility, so a name whose
# residual is near zero attracts a near-infinite weight. A name that moves almost exactly
# with the factor has no idiosyncratic component to own, and its measured "residual" is
# estimation noise and floating-point residue. Without this floor the book's largest
# position is reliably its least meaningful one - which is not a hypothetical: it was
# caught by the test that builds a world with no residual at all and expected the system
# to stand aside. It did not. It took a position in rounding error.
MIN_RESID_SHARE = 0.05


@dataclass(frozen=True)
class FactorSet:
    """Which return the residual is taken against.

    A residual is only defined relative to something. `BTC_ONLY` is the design's declared
    starting point: it is the factor Makarov and Schoar actually measured, it needs no
    construction of our own, and a factor we build ourselves is a factor we can overfit.
    Richer sets (the published three-factor models) are a deliberate later step and the
    design says so out loud.
    """

    name: str
    symbols: tuple[str, ...]
    ex_self: bool = False

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("a factor set with no symbols cannot define a residual")

    def constituents(self, exclude: str | None = None) -> tuple[str, ...]:
        """The constituents used for one asset's factor, self-excluded when asked.

        WHY EX-SELF EXISTS AT ALL

        A market factor is the equal-weight mean of the cross-section, which means every
        traded name is inside its own explanatory variable. `residuals()` refuses to
        residualise a symbol on a set containing itself, and it is right to: the loading
        goes toward one, the residual toward zero, and a book that sizes by inverse
        residual volatility then takes an unbounded position in it. That refusal is what
        makes an all-names factor unusable as written - it would leave zero tradable
        symbols.

        Excluding the asset from its own factor is the standard construction and it
        removes the bias rather than hiding it. With thirty-two names the self weight is
        3.1%, which is small and is exactly the part that mechanically inflates beta.
        """
        if not self.ex_self or exclude is None:
            return self.symbols
        return tuple(s for s in self.symbols if s != exclude)


BTC_ONLY = FactorSet("btc_only", ("BTCUSDT",))


def market_ex_self(symbols) -> FactorSet:
    """The equal-weight cross-section as the factor, each name excluded from its own.

    BTC as the sole factor is the design's declared starting point and it has a known
    weakness: it is one asset, so everything the rest of the market does together lands
    in the residual and is then read as idiosyncratic. A book that ranks on that residual
    is partly ranking on shared market moves wearing an idiosyncratic label.
    """
    syms = tuple(sorted(set(str(s) for s in symbols)))
    if len(syms) < 3:
        raise ValueError("a market factor needs at least three names to be a market")
    return FactorSet("market_ex_self", syms, ex_self=True)


def daily_closes(bars) -> dict[str, float]:
    """Last close per UTC day. The key is the date string, so days align across symbols.

    Taking the LAST close of the day rather than a fixed hour means a symbol with a gap
    in its 15m tape still contributes a day, which matters because our tapes are not all
    equally complete and silently dropping days would change the universe by stealth.
    """
    out: dict[str, float] = {}
    for b in bars:
        out[b.timestamp.strftime("%Y-%m-%d")] = float(b.close)
    return out


def daily_turnover(bars) -> dict[str, float]:
    """Traded USD per UTC day: sum of volume x close over the day's bars.

    Base-unit volume is not comparable across symbols - a thousand DOGE and a thousand BTC
    are not the same amount of market - so size and liquidity have to be measured in
    money. Summed rather than averaged, because the question this answers is how much
    could be traded in a day, not how much moved in an average bar.
    """
    out: dict[str, float] = {}
    for b in bars:
        day = b.timestamp.strftime("%Y-%m-%d")
        out[day] = out.get(day, 0.0) + float(b.volume) * float(b.close)
    return out


def simple_returns(closes: dict[str, float]) -> dict[str, float]:
    """Day-over-day SIMPLE returns. See the module docstring for why not log."""
    days = sorted(closes)
    out: dict[str, float] = {}
    for prev, day in zip(days, days[1:]):
        p0, p1 = closes[prev], closes[day]
        if p0 > 0 and p1 > 0:
            out[day] = p1 / p0 - 1.0
    return out


def factor_return(rets: dict[str, dict[str, float]], factors: FactorSet,
                  day: str, exclude: str | None = None) -> float | None:
    """The factor's return on one day: the equal-weight mean of its constituents.

    Returns None when no constituent has a return that day, which is the honest answer -
    a missing factor is not a zero factor, and treating it as zero would hand every
    asset a residual equal to its raw return on exactly the days the tape is worst.

    `exclude` drops one name from its own factor. It does nothing unless the factor set
    was built with `ex_self`, so a caller cannot silently change what BTC_ONLY means.
    """
    syms = factors.constituents(exclude)
    vals = [rets[s][day] for s in syms if s in rets and day in rets[s]]
    return float(np.mean(vals)) if vals else None


def _factor_series(rets: dict[str, dict[str, float]], factors: FactorSet,
                   exclude: str | None = None) -> dict[str, float]:
    """The factor's return for every day it is defined, for one asset's point of view."""
    days = sorted({d for s in factors.constituents(exclude) if s in rets
                   for d in rets[s]})
    out = {}
    for d in days:
        fr = factor_return(rets, factors, d, exclude=exclude)
        if fr is not None:
            out[d] = fr
    return out


@dataclass(frozen=True)
class Loading:
    """One causal factor loading, and the evidence behind it.

    `through` is the last day INSIDE the estimation window. It is carried because the
    single most expensive bug available in this design is an off-by-one that lets the
    window touch the bar being explained, and a field that records where the window
    stopped turns that bug into an assertion.
    """

    day: str
    beta: float
    resid_vol: float
    obs: int
    through: str


def loadings(asset: dict[str, float], factor: dict[str, float],
             window: int = DEFAULT_WINDOW,
             min_obs: int = MIN_OBS,
             min_resid_share: float = MIN_RESID_SHARE) -> dict[str, Loading]:
    """Causal rolling loading of one asset on the factor, per day.

    For day `d`, the regression uses the `window` most recent COMMON days that are
    STRICTLY BEFORE `d`. Nothing from `d` enters. The returned `Loading.through` is the
    newest day that did enter, and `through < day` is guaranteed - there is a test that
    asserts it on every day of a real tape, because "I was careful" is not a control.

    `resid_vol` is the in-window standard deviation of the residual, which is what the
    book sizes by. Scaling by residual volatility rather than price volatility is a claim
    of the design, not a convention: the book intends to own the residual, so the risk it
    should equalise is the residual's.
    """
    days = sorted(set(asset) & set(factor))
    out: dict[str, Loading] = {}
    if len(days) <= min_obs:
        return out

    a = np.array([asset[d] for d in days], dtype=float)
    f = np.array([factor[d] for d in days], dtype=float)

    for i in range(min_obs, len(days)):
        lo = max(0, i - window)
        wa, wf = a[lo:i], f[lo:i]          # [lo, i) - excludes day i by construction
        if len(wa) < min_obs:
            continue
        var = float(np.var(wf))
        if var <= 0:
            continue
        beta = float(np.cov(wa, wf, bias=True)[0, 1]) / var
        resid = wa - beta * wf
        sd = float(np.std(resid, ddof=1)) if len(resid) > 1 else 0.0
        if sd <= 0:
            continue
        # The residual must be a real share of the asset's own movement. A name that
        # tracks the factor almost exactly has nothing idiosyncratic to own, and sizing
        # by inverse residual volatility would hand it the largest position in the book.
        own = float(np.std(wa, ddof=1)) if len(wa) > 1 else 0.0
        if own <= 0 or sd < min_resid_share * own:
            continue
        out[days[i]] = Loading(days[i], beta, sd, len(wa), days[i - 1])
    return out


def residuals(rets: dict[str, dict[str, float]], factors: FactorSet = BTC_ONLY,
              window: int = DEFAULT_WINDOW,
              min_obs: int = MIN_OBS,
              min_resid_share: float = MIN_RESID_SHARE) -> dict[str, dict[str, Loading]]:
    """Loadings for every non-factor symbol. The factor cannot be residualised on itself.

    Excluding the factor's own constituents is not tidiness. A symbol regressed on a set
    containing itself gets a loading near one and a residual near zero, and a book that
    sizes by residual volatility would then take an unbounded position in it.
    """
    shared = None if factors.ex_self else _factor_series(rets, factors)

    out: dict[str, dict[str, Loading]] = {}
    for sym, series in rets.items():
        if factors.ex_self:
            # Every name is tradable here, because none of them is inside its own factor.
            factor_series = _factor_series(rets, factors, exclude=sym)
        else:
            if sym in factors.symbols:
                continue
            factor_series = shared
        got = loadings(series, factor_series, window=window, min_obs=min_obs,
                       min_resid_share=min_resid_share)
        if got:
            out[sym] = got
    return out


def residual_return(asset_return: float, beta: float, factor_ret: float) -> float:
    """eps = r_i - beta * r_factor. One line, named, so it is impossible to get the
    sign wrong twice in different places."""
    return asset_return - beta * factor_ret


def residual_series(rets: dict[str, dict[str, float]],
                    loads: dict[str, dict[str, Loading]],
                    factors: FactorSet = BTC_ONLY) -> dict[str, dict[str, float]]:
    """The realised residual per symbol per day, using the loading known BEFORE the day.

    This is the series the signal is computed on. It exists as its own function so that a
    test can compare it against a hand-computed value rather than against the book's
    output, where a sign error would be hidden by everything else.
    """
    shared = None if factors.ex_self else _factor_series(rets, factors)

    out: dict[str, dict[str, float]] = {}
    for sym, per_day in loads.items():
        factor_series = (_factor_series(rets, factors, exclude=sym)
                         if factors.ex_self else shared)
        series = rets.get(sym, {})
        eps: dict[str, float] = {}
        for day, load in per_day.items():
            if day in series and day in factor_series:
                eps[day] = residual_return(series[day], load.beta, factor_series[day])
        if eps:
            out[sym] = eps
    return out


def as_datetime(day: str) -> datetime:
    return datetime.strptime(day, "%Y-%m-%d")
