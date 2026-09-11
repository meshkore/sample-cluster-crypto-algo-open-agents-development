"""The statistical guards. These exist because of this laboratory's own history.

Six systems were promoted here. Every one was positive across the research years and
negative in the same forward year. That is not six independent mistakes - it is one
method failing six times, and the method was: try many configurations, keep the best,
report its Sharpe as if it were the only one tried.

The literature has a name and a correction for exactly that.

  Harvey, Liu and Zhu argue a new factor should clear roughly t > 3 rather than the
  conventional 1.96, because the factor zoo is a multiple-testing problem.

  Bailey and Lopez de Prado's DEFLATED SHARPE RATIO corrects an observed Sharpe for
  selection bias over the number of trials ACTUALLY RUN, for sample length, and for
  non-normality (skew and kurtosis), which crypto has in quantity.

  Bailey, Borwein, Lopez de Prado and Zhu's PROBABILITY OF BACKTEST OVERFITTING describes
  the failure directly: the more configurations you try, the more certain it becomes that
  the winner was selected rather than discovered.

THE RULE THIS MODULE ENFORCES

`trials` is not optional and it is not allowed to be 1 by default. A caller must state
how many configurations were tried to arrive at the number being deflated. Understating
it is the easiest way to make this guard say what you want, so it is passed explicitly,
recorded in the output, and a caller that lies is lying on the record.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Harvey, Liu & Zhu's hurdle for a new factor, rather than the conventional 1.96.
T_HURDLE = 3.0
# Euler-Mascheroni, used in the expected-maximum-Sharpe term of the deflated ratio.
_EULER = 0.5772156649015329


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse normal CDF, Acklam's rational approximation. Accurate to ~1e-9, which is
    several orders more than a Sharpe estimate deserves."""
    if not 0.0 < p < 1.0:
        raise ValueError("probability must be in (0, 1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q, r = p - 0.5, (p - 0.5) ** 2
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def moments(returns: list[float]) -> tuple[float, float, float, float]:
    """Mean, standard deviation, skew and KURTOSIS (not excess) of a return series."""
    n = len(returns)
    if n < 3:
        return 0.0, 0.0, 0.0, 3.0
    mu = sum(returns) / n
    var = sum((r - mu) ** 2 for r in returns) / (n - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return mu, 0.0, 0.0, 3.0
    m3 = sum((r - mu) ** 3 for r in returns) / n
    m4 = sum((r - mu) ** 4 for r in returns) / n
    pop_sd = math.sqrt(sum((r - mu) ** 2 for r in returns) / n)
    return mu, sd, m3 / pop_sd ** 3, m4 / pop_sd ** 4


def sharpe(returns: list[float], periods_per_year: int = 365) -> float:
    mu, sd, _, _ = moments(returns)
    if sd <= 0:
        return 0.0
    return (mu / sd) * math.sqrt(periods_per_year)


def t_statistic(returns: list[float]) -> float:
    mu, sd, _, _ = moments(returns)
    if sd <= 0 or not returns:
        return 0.0
    return mu / (sd / math.sqrt(len(returns)))


@dataclass(frozen=True)
class Deflated:
    sharpe: float
    deflated_sharpe: float
    probability: float
    t_stat: float
    trials: int
    observations: int
    skew: float
    kurtosis: float

    @property
    def clears_hurdle(self) -> bool:
        """Both guards, and both must pass. The t-hurdle catches a result that is merely
        noisy; the deflated Sharpe catches one that is merely selected. A strategy can
        fail either way and they are different failures."""
        return self.t_stat > T_HURDLE and self.probability > 0.95


def expected_max_sharpe(trials: int, variance_of_trials: float = 1.0) -> float:
    """Expected maximum Sharpe from `trials` independent draws of zero-skill strategies.

    This is the number that makes the deflated Sharpe work: if you try enough things,
    the best of them looks good FOR FREE, and this says how good. Trying 100 variations
    and keeping the best is not a discovery unless it beats this.
    """
    if trials < 2:
        return 0.0
    sd = math.sqrt(max(variance_of_trials, 1e-12))
    a = _norm_ppf(1.0 - 1.0 / trials)
    b = _norm_ppf(1.0 - 1.0 / (trials * math.e))
    return sd * ((1.0 - _EULER) * a + _EULER * b)


def deflated_sharpe(returns: list[float], trials: int,
                    periods_per_year: int = 365,
                    variance_of_trials: float = 1.0) -> Deflated:
    """Bailey & Lopez de Prado's deflated Sharpe ratio.

    `trials` MUST be the number of configurations actually tried to arrive at this
    result. There is no default. Passing 1 when fifty were swept does not make the
    result better, it makes the report false, and it is the specific lie this
    laboratory's six dead systems were built on.
    """
    if trials < 1:
        raise ValueError("trials must be at least 1 - state how many were tried")
    n = len(returns)
    if n < 30:
        return Deflated(0.0, 0.0, 0.0, 0.0, trials, n, 0.0, 3.0)

    _, _, skew, kurt = moments(returns)
    sr = sharpe(returns, periods_per_year)
    # Work in per-period units, which is where the variance formula is defined.
    sr_p = sr / math.sqrt(periods_per_year)
    sr0 = expected_max_sharpe(trials, variance_of_trials) if trials > 1 else 0.0

    denom = 1.0 - skew * sr_p + ((kurt - 1.0) / 4.0) * sr_p ** 2
    if denom <= 0:
        # Heavy enough tails that the estimator's own variance is undefined. Reporting
        # zero confidence is the honest answer, not a clamped one.
        return Deflated(sr, 0.0, 0.0, t_statistic(returns), trials, n, skew, kurt)

    z = (sr_p - sr0) * math.sqrt(n - 1) / math.sqrt(denom)
    return Deflated(sr, (sr_p - sr0) * math.sqrt(periods_per_year), _norm_cdf(z),
                    t_statistic(returns), trials, n, skew, kurt)
