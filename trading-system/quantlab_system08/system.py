"""System 08 assembled: the residual book, end to end.

This module does the wiring and nothing clever. Every decision worth arguing lives in
`residual.py`, `signal.py`, `book.py` or `stats.py`, and it lives there precisely so that
this file cannot quietly become the place where a parameter is born.

THE SYSTEM IN ONE SENTENCE

Hold the residual of a large-capitalisation crypto book after hedging out the common
factor, and size it by cross-sectional momentum OF THAT RESIDUAL, long and short.

THE ORDER OF OPERATIONS, WHICH IS THE PART THAT CAN BE WRONG

    day d-1 and earlier  ->  returns, loadings, residuals, momentum scores
    day d, at the open   ->  rebalance to the new targets, pay the turnover
    day d, over the day  ->  earn the day's returns, accrue funding

Nothing computed on day `d` is allowed to decide a position held on day `d`. That is the
single most expensive bug available in this design and it is asserted by a test rather
than promised by a comment.

WHAT THE RUN REFUSES TO DO

Read 2026. `quantlab_catalog.research()` cannot return a sealed bar - the lock is
structural, not a convention - and this module never calls `forward()`. Reading the
sealed year is a separate, deliberate, visible act that has to be earned first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from . import residual as R
from . import signal as S
from .book import BookResult, daily_funding, run_book
from .stats import deflated_sharpe

# How often the book re-ranks. Two weeks, matching the horizon of the crypto momentum
# factor that actually survived selection in the literature.
DEFAULT_REBALANCE_DAYS = S.DEFAULT_HOLD_DAYS


@dataclass(frozen=True)
class Config:
    """Every knob in one frozen object, so a run is reproducible from its own report.

    It is deliberately small. Each additional field multiplies the configuration space,
    and the size of that space is what the deflated Sharpe has to be corrected for - so
    a knob added here makes every future result statistically weaker. Adding one should
    feel expensive, because it is.
    """

    factor: str = "btc_only"
    window: int = R.DEFAULT_WINDOW
    lookback: int = S.DEFAULT_LOOKBACK_DAYS
    skip: int = S.DEFAULT_SKIP_DAYS
    hold: int = DEFAULT_REBALANCE_DAYS
    side_fraction: float = S.DEFAULT_SIDE_FRACTION
    gross_cap: float = S.DEFAULT_GROSS_CAP
    initial_equity: float = 100_000.0

    def factor_set(self) -> R.FactorSet:
        if self.factor != "btc_only":
            raise ValueError(
                f"unknown factor set {self.factor!r}. Richer sets (the published "
                f"three-factor models) are a deliberate later step, and the design "
                f"registered the choice as a decision rather than a default.")
        return R.BTC_ONLY


@dataclass
class Run:
    config: Config
    result: BookResult
    symbols: list[str]
    factor_symbol: str
    rebalances: int
    trials: int

    def report(self) -> dict:
        r = self.result
        stats = deflated_sharpe(r.returns(), trials=self.trials)
        years = r.by_year()
        return {
            "system": "system08",
            "at": datetime.now(timezone.utc).isoformat(),
            "config": asdict(self.config),
            "universe": self.symbols,
            "factor": self.factor_symbol,
            "span": [r.days[0].day, r.days[-1].day] if r.days else [],
            "days": len(r.days),
            "rebalances": self.rebalances,
            "total_return": r.total_return,
            "max_drawdown": r.max_drawdown,
            "total_costs": r.total_costs,
            "funding_received": r.total_funding,
            "by_year": years,
            "years_positive": sum(1 for v in years.values() if v > 0),
            "years": len(years),
            "sharpe": stats.sharpe,
            "deflated_sharpe": stats.deflated_sharpe,
            "deflated_probability": stats.probability,
            "t_stat": stats.t_stat,
            "trials_declared": stats.trials,
            "clears_statistical_hurdle": stats.clears_hurdle,
        }


def load(symbols: list[str] | None = None) -> tuple[list[str], dict]:
    """Universe and research bars from the shared catalogue. Never the sealed year."""
    import quantlab_catalog as cat
    from quantlab_catalog.paths import universe_file

    meta = json.loads(universe_file().read_text(encoding="utf-8"))
    S.require_screened_universe(meta)

    syms = symbols or cat.load_universe()
    return list(syms), cat.research(syms)


def build(bars_by_symbol: dict, config: Config = Config(),
          trials: int = 1) -> Run:
    """Assemble and run the book on already-loaded bars.

    Taking bars as an argument rather than loading them keeps this function pure enough
    to test against a synthetic tape, which is the only way to assert the causality
    property on data whose answer is known.
    """
    factors = config.factor_set()
    factor_symbol = factors.symbols[0]

    rets = {s: R.simple_returns(R.daily_closes(bars))
            for s, bars in bars_by_symbol.items() if bars}
    loads = R.residuals(rets, factors=factors, window=config.window)
    eps = R.residual_series(rets, loads, factors=factors)
    if not eps:
        raise ValueError("no residual series could be built - check the tape and window")

    all_days = sorted({d for s in rets.values() for d in s})

    # Rebalance days: a fixed cadence from the first day any name has a usable signal.
    # A fixed cadence rather than an event trigger is a deliberate choice - an event
    # trigger is another parameter, and the horizon is already set by the literature.
    first_ready = min(min(per_day) for per_day in loads.values())
    start = all_days.index(first_ready) if first_ready in all_days else 0
    reb_days = all_days[start::config.hold]

    targets_on: dict[str, list] = {}
    hedge_on: dict[str, float] = {}
    for day in reb_days:
        # Everything read here is strictly before `day`: the loading window ends at
        # day-1 by construction, and the momentum window ends `skip` days earlier still.
        vols = {s: per_day[day].resid_vol for s, per_day in loads.items()
                if day in per_day}
        betas = {s: per_day[day].beta for s, per_day in loads.items() if day in per_day}
        if not vols:
            continue
        tg = S.targets_for_day(eps, vols, day, lookback=config.lookback,
                               skip=config.skip, side_fraction=config.side_fraction,
                               gross_cap=config.gross_cap)
        if not tg:
            # Standing aside is a position, and an empty target vector is the honest
            # way to express it: the next loop flattens the book and pays to do so.
            targets_on[day], hedge_on[day] = [], 0.0
            continue
        targets_on[day] = tg
        hedge_on[day] = S.hedge_weight(tg, betas)

    import quantlab_catalog as cat
    funding = {}
    for s in list(rets) + [factor_symbol]:
        try:
            rows = cat.funding(s)
        except Exception:
            continue
        if rows:
            funding[s] = daily_funding(rows)

    traded_days = [d for d in all_days if d >= reb_days[0]] if reb_days else []
    result = run_book(traded_days, rets, targets_on, hedge_on, factor_symbol,
                      funding=funding, initial_equity=config.initial_equity,
                      gross_cap=config.gross_cap)
    return Run(config, result, sorted(rets), factor_symbol,
               sum(1 for v in targets_on.values() if v), trials)


def write_report(run: Run, out_dir: str | Path = "research/system08/runs") -> Path:
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    target = path / f"run_{stamp}.json"
    target.write_text(json.dumps(run.report(), indent=1, default=str), encoding="utf-8")
    return target
