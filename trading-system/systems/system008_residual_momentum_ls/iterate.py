"""One numbered iteration = one full cycle: research backtest, then the sealed 2026 read.

WHY ITERATIONS ARE NUMBERED AND WRITTEN DOWN

The operator asked to see, on the live page, how each attempt went - the research result up
to 2025 and the forward result on 2026 - "whether they are good or bad". That phrase is the
point of this module. An iteration record is written BEFORE anyone knows whether they like
it, it carries its own configuration, and it is never edited afterwards. A laboratory that
only records the runs it liked has no record at all, and this one already spent six systems
learning that.

WHAT A CYCLE IS

    research   every bar strictly before the 2026 lock. Nothing here can see the future;
               the catalogue's lock is structural, so `research()` CANNOT return a sealed
               bar even if a caller asks wrongly.

    forward    2026 alone, run with the research history in front of it so the rolling
               window is already warm when the first sealed bar arrives. Equity is REBASED
               at the lock so the forward number stands on its own and is not flattered by
               whatever the research years happened to compound to.

THE COST OF THE SEALED READ, STATED PLAINLY

2026 is read here, and reading it is irreversible: every look spends a little of its
value as an out-of-sample test. It is spent deliberately, on the operator's instruction, and
it is spent on the cleanest possible subject - a v1 in which **no parameter was ever swept**.
There is no configuration selected on research performance, so nothing about this forward
read is contaminated by selection. That is the only circumstance in which spending it is
cheap, and it will not be true again once tuning starts.

THE RULE FOR EVERY FUTURE ITERATION

`trials` must count every configuration tried to date, across all iterations, not the one
being reported. The deflated Sharpe is corrected against that count, and understating it is
the specific lie the six dead systems were built on.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .book import BookResult, DayRecord
from .stats import deflated_sharpe
from .system import DEFAULT_UNIVERSE, Config, build

ITERATIONS = Path("research/system08/iterations")
LOCK_YEAR = 2026


def _segment(result: BookResult, since_year: int | None = None,
             before_year: int | None = None) -> BookResult:
    """Slice a run into an era and REBASE its equity so the slice stands alone.

    Without rebasing, a forward return would be measured against an equity the research
    years produced, which makes a good research run flatter its own forward test and a bad
    one punish it. The two eras have to be readable independently or the comparison the
    operator asked for does not mean anything.
    """
    days = [d for d in result.days
            if (since_year is None or int(d.day[:4]) >= since_year)
            and (before_year is None or int(d.day[:4]) < before_year)]
    if not days:
        return BookResult(days=[], initial_equity=result.initial_equity)

    base = days[0].equity / (1.0 + 0.0)
    # The opening equity of the slice is the equity BEFORE its first day, which is the
    # previous day's close - or the run's initial equity when the slice starts the run.
    idx = result.days.index(days[0])
    opening = result.days[idx - 1].equity if idx > 0 else result.initial_equity
    scale = result.initial_equity / opening if opening > 0 else 1.0

    rebased = [DayRecord(d.day, d.equity * scale, d.gross, d.net,
                         d.asset_pnl, d.hedge_pnl, d.funding_pnl, d.cost,
                         d.n_long, d.n_short, d.rebalanced) for d in days]
    del base
    return BookResult(days=rebased, initial_equity=result.initial_equity)


def _summarise(result: BookResult, trials: int) -> dict:
    if not result.days:
        return {"days": 0, "note": "no days in this era"}
    stats = deflated_sharpe(result.returns(), trials=trials)
    years = result.by_year()
    return {
        "span": [result.days[0].day, result.days[-1].day],
        "days": len(result.days),
        "total_return": result.total_return,
        "max_drawdown": result.max_drawdown,
        "total_costs": result.total_costs,
        "funding_received": result.total_funding,
        "by_year": {str(k): v for k, v in years.items()},
        "years_positive": sum(1 for v in years.values() if v > 0),
        "years": len(years),
        "sharpe": stats.sharpe,
        "t_stat": stats.t_stat,
        "deflated_probability": stats.probability,
        "clears_statistical_hurdle": stats.clears_hurdle,
        "rebalances": sum(1 for d in result.days if d.rebalanced),
    }


def next_number(root: Path = ITERATIONS) -> int:
    root.mkdir(parents=True, exist_ok=True)
    used = [int(p.stem) for p in root.glob("*.json") if p.stem.isdigit()]
    return (max(used) + 1) if used else 1


def run_cycle(config: Config = Config(), trials: int = 1,
              title: str = "", note: str = "",
              root: Path = ITERATIONS,
              universe: str = DEFAULT_UNIVERSE) -> dict:
    """Run one complete cycle and write its numbered record.

    The record is written whatever the outcome. There is no branch in this function that
    decides not to save a result, and there should never be one.

    `universe` names the snapshot rather than the symbols, and the name is stored in the
    record: two cycles with the same configuration and different cross-sections are two
    different experiments, and a record that does not say which one it ran is not a record.
    A symbol the local store cannot serve is dropped here and LISTED, because a universe
    file that promises a name the loader silently skips changes the experiment without
    changing the file that declares it.
    """
    import quantlab_catalog as cat
    from quantlab_catalog.paths import universe_file
    from . import signal as S

    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    S.require_screened_universe(meta)
    declared = [str(x) for x in meta["symbols"]]

    # --- research: strictly before the lock, by construction.
    research_bars = cat.research(declared)
    symbols = [s for s in declared if research_bars.get(s)]
    dropped = [s for s in declared if s not in symbols]
    research_bars = {s: research_bars[s] for s in symbols}
    research_run = build(research_bars, config, trials=trials)

    # --- forward: the sealed year, warmed by the history in front of it. Keyword-only,
    # so it can never be switched on by accident.
    combined = cat.candles(symbols, include_sealed=True)
    combined_run = build(combined, config, trials=trials)
    forward = _segment(combined_run.result, since_year=LOCK_YEAR)

    number = next_number(root)
    record = {
        "iteration": number,
        "system": "system08",
        "title": title or "The residual book - first complete cycle",
        "note": note,
        "at": datetime.now(timezone.utc).isoformat(),
        "config": asdict(config),
        "universe_file": universe,
        "universe_declared": len(declared),
        "universe_dropped": dropped,
        "universe": research_run.symbols,
        "factor": research_run.factor_symbol,
        "trials_declared": trials,
        "research": _summarise(research_run.result, trials),
        "forward_2026": _summarise(forward, trials),
        "sealed_read": True,
        "sealed_note": ("2026 was read deliberately and once. No parameter was swept to "
                        "produce this configuration, so nothing in the forward number is "
                        "contaminated by selection - which will stop being true the "
                        "moment tuning starts."),
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{number:03d}.json").write_text(
        json.dumps(record, indent=1, default=str), encoding="utf-8")
    return record


def load_all(root: Path = ITERATIONS) -> list[dict]:
    """Every iteration ever recorded, oldest first. Nothing is filtered out."""
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return sorted(out, key=lambda r: r.get("iteration", 0))
