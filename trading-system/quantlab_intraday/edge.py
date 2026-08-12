"""Does the signal have an edge at all, before any portfolio hides the answer?

A backtest answers "did this configuration make money", which is a different
and much later question than "does the thing this system claims to detect
actually predict anything". Running the second question through the first is
how a laboratory spends a week tuning stops on a signal with no information in
it, and this project has a measured reason to insist on the order: Phase-1 rank
correlates +0.06 with forward rank, so a number produced by search is close to
uninformative on its own.

So this module strips everything away. No portfolio, no sizing, no drawdown, no
concurrency limit. For every bar that qualifies, it records what price did over
the next N bars if you had bought at the next open exactly as the session would
have filled you, and compares that to what price did after *every* bar. Three
columns decide whether any of this is worth continuing:

- **gross** -- the mean forward return after a qualifying bar;
- **baseline** -- the mean forward return after any bar at all. An entry rule
  that beats zero in a market that rose 40% that year has found the market, not
  an edge, and this column is what separates the two;
- **net** -- gross minus the 30 bps round trip. This is the only one that is
  real money, and at 15-minute resolution it is usually the one that kills the
  idea.

The per-year table exists for one specific claim. This system says its edge is
a liquidity premium, which is paid in any market, rather than a directional
bet, which is not. That predicts the yearly numbers should have the same sign
in falling years as in rising ones. If they do not, the hypothesis is refuted
however good the aggregate looks, and the aggregate would then be a bull-market
result with extra steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from quantlab_backtester.indicators import IndicatorSpec, panel_for
from quantlab_backtester.models import Bar

from . import context, microstructure
from .moneymanagement import bar_turnover_floor, round_trip_cost

DEFAULT_HORIZONS = (1, 2, 4, 8, 16, 32, 96)


@dataclass
class Sample:
    """Forward returns collected at one horizon."""

    horizon: int
    values: list[float] = field(default_factory=list)

    def add(self, value: float) -> None:
        self.values.append(value)

    def document(self, cost: float) -> dict[str, Any]:
        if not self.values:
            return {"horizon": self.horizon, "n": 0}
        n = len(self.values)
        mean = sum(self.values) / n
        wins = sum(1 for value in self.values if value > 0)
        # Sample standard deviation, then the standard error of the mean. A
        # mean of +8 bps over 300 observations and the same mean over 30,000
        # are different claims, and without this column they print identically.
        variance = sum((value - mean) ** 2 for value in self.values) / max(n - 1, 1)
        deviation = variance**0.5
        return {
            "horizon": self.horizon,
            "n": n,
            "gross_mean": mean,
            "net_mean": mean - cost,
            "win_rate": wins / n,
            "stdev": deviation,
            "stderr": deviation / (n**0.5),
            # How many standard errors the NET mean is from zero. Under 2 there
            # is nothing here, whatever the sign says.
            "net_t": ((mean - cost) / (deviation / (n**0.5))) if deviation else 0.0,
        }


def scan(
    bars_by_symbol: dict[str, list[Bar]],
    *,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    minimum_displacement_atr: float = 1.5,
    maximum_ibs: float = 0.30,
    maximum_rsi: float = 15.0,
    cost_multiple: float = 2.0,
    volatility_quantile: float = 0.95,
    minimum_daily_turnover: float = 10_000_000.0,
    bars_per_day: int = 96,
    spec: IndicatorSpec | None = None,
    commission_bps: float = 10.0,
    slippage_bps: float = 5.0,
) -> dict[str, Any]:
    """Measure the signal on its own, symbol by symbol, year by year.

    Entry and exit prices are the ones the session would actually use: a
    decision is made on a closed bar and filled at the NEXT bar's open, so the
    entry is `open[i+1]` and the exit `open[i+1+h]`. Measuring from `close[i]`
    instead would quietly hand the study the very move it is trying to detect,
    which is the single most common way an intraday backtest lies.
    """
    spec = spec or IndicatorSpec()
    cost = round_trip_cost(commission_bps, slippage_bps)
    hurdle = cost * cost_multiple
    turnover_floor = bar_turnover_floor(minimum_daily_turnover, bars_per_day)
    horizons = tuple(sorted(horizons))

    signal = {horizon: Sample(horizon) for horizon in horizons}
    # The same observations, thinned so no two of them overlap. See the note on
    # `independent` in the returned document: this is the column to read, and
    # the reason is that the obvious one lies.
    independent = {horizon: Sample(horizon) for horizon in horizons}
    baseline = {horizon: Sample(horizon) for horizon in horizons}
    by_year: dict[int, Sample] = {}
    by_symbol: dict[str, Sample] = {}
    refusals: dict[str, int] = {}
    reference = max(horizons)

    for symbol, bars in sorted(bars_by_symbol.items()):
        if len(bars) < reference + 2:
            continue
        panel = panel_for(bars, spec)
        watch = context.VolatilityWatch()
        last_taken = {horizon: -(10**9) for horizon in horizons}
        for index in range(panel.warmup_bars, len(bars) - reference - 1):
            row = panel.at(index)
            bar = bars[index]
            watch.observe(symbol, row.get("natr_14"))
            entry = bars[index + 1].open
            if entry <= 0:
                continue
            for horizon in horizons:
                baseline[horizon].add(bars[index + 1 + horizon].open / entry - 1)

            reading = microstructure.read(
                symbol,
                {
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                },
                row,
            )
            if reading is None:
                continue
            verdict = microstructure.qualifies(
                reading,
                minimum_displacement_atr=minimum_displacement_atr,
                maximum_ibs=maximum_ibs,
                maximum_rsi=maximum_rsi,
                cost_hurdle_pct=hurdle,
                minimum_turnover=turnover_floor,
            )
            if not verdict.ok:
                refusals[verdict.reason] = refusals.get(verdict.reason, 0) + 1
                continue
            if watch.elevated(symbol, row.get("natr_14"), volatility_quantile):
                refusals["volatility"] = refusals.get("volatility", 0) + 1
                continue

            for horizon in horizons:
                value = bars[index + 1 + horizon].open / entry - 1
                signal[horizon].add(value)
                if index >= last_taken[horizon] + horizon:
                    independent[horizon].add(value)
                    last_taken[horizon] = index
            year = bar.timestamp.year
            by_year.setdefault(year, Sample(reference))
            by_year[year].add(bars[index + 1 + reference].open / entry - 1)
            by_symbol.setdefault(symbol, Sample(reference))
            by_symbol[symbol].add(bars[index + 1 + reference].open / entry - 1)

    return {
        "round_trip_cost": cost,
        "cost_hurdle": hurdle,
        "turnover_floor": turnover_floor,
        "reference_horizon": reference,
        "signal": [signal[horizon].document(cost) for horizon in horizons],
        # THE t-STATISTIC TO QUOTE. `signal` samples every qualifying bar, so
        # at a 288-bar horizon on 5-minute candles a single day's move is
        # counted by up to 288 overlapping observations that are nearly the
        # same number. The standard error then divides by the square root of a
        # sample size that does not exist, and a mean of +0.19% arrived with
        # t = 6.7 -- which is what a real edge and a heavily autocorrelated
        # nothing look like when they are printed by the same formula. These
        # are the same observations thinned so that no window overlaps another:
        # fewer rows and honest error bars. The thinned MEAN is a subsample's
        # mean and may sit anywhere inside its own (wider) error bar -- that is
        # the noise being admitted rather than hidden, not a discrepancy.
        # Selection is by position in time only, never by value, so nothing is
        # dropped for being inconvenient.
        "independent": [independent[horizon].document(cost) for horizon in horizons],
        "baseline": [baseline[horizon].document(0.0) for horizon in horizons],
        "by_year": {year: by_year[year].document(cost) for year in sorted(by_year)},
        "by_symbol": {
            symbol: by_symbol[symbol].document(cost) for symbol in sorted(by_symbol)
        },
        "refusals": refusals,
    }


def table(report: dict[str, Any]) -> str:
    """The scan as something a person can read in ten seconds."""
    lines = [
        f"round trip {report['round_trip_cost']:.2%}, "
        f"hurdle {report['cost_hurdle']:.2%}, "
        f"turnover floor ${report['turnover_floor']:,.0f}/bar",
        "",
        f"{'bars':>6}{'n':>9}{'gross':>10}{'net':>10}{'t':>7}"
        f"{'indep n':>9}{'t*':>7}{'win%':>7}{'baseline':>11}",
        "-" * 76,
    ]
    baselines = {row["horizon"]: row for row in report["baseline"]}
    honest = {row["horizon"]: row for row in report.get("independent", [])}
    for row in report["signal"]:
        if not row.get("n"):
            continue
        base = baselines.get(row["horizon"], {})
        thin = honest.get(row["horizon"], {})
        lines.append(
            f"{row['horizon']:>6}{row['n']:>9,}"
            f"{row['gross_mean']:>10.3%}{row['net_mean']:>10.3%}"
            f"{row['net_t']:>7.1f}{thin.get('n', 0):>9,}"
            f"{thin.get('net_t', 0.0):>7.1f}{row['win_rate']:>7.0%}"
            f"{base.get('gross_mean', 0.0):>11.3%}"
        )
    lines += [
        "",
        f"by year (horizon {report['reference_horizon']} bars) -- read the SIGN",
        "and the magnitude. These rows are every observation, so their t is",
        "overlap-inflated in the same way the `t` column above is; only `t*`",
        "is thinned. The year table exists to answer whether the sign flips",
        "with the market cycle, which no error bar is needed to see.",
        "-" * 60,
    ]
    for year, row in report["by_year"].items():
        if not row.get("n"):
            continue
        lines.append(
            f"{year:>6}{row['n']:>9,}{row['gross_mean']:>10.3%}"
            f"{row['net_mean']:>10.3%}{row['win_rate']:>7.0%}"
        )
    return "\n".join(lines)
