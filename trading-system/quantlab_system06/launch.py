"""Run system06 through the frozen instrument: the training era and sealed 2026.

Driven in-process against the same `BacktestSession` the server instantiates —
identical fills, costs, next-bar-open rule and warm-up trimming — for the reason
the intraday system documents: the sealed 2026 window at 15-minute resolution is
far past the server's 4 MB request cap, and splitting it would break the
account's continuity. The one thing skipped is the HTTP hop; the wire is covered
by the backtester's own tests.

Two halves of one hypothesis. Both are built from the same brain genome and
differ only in `trade_from`, so the monitor can pair them. `infer.py` must have
written `signals.npz` first — the brain reads it and holds no model.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantlab_backtester.backtest import CostModel
from quantlab_backtester.ledger import BacktestRun
from quantlab_backtester.models import Bar, utc_now
from quantlab_backtester.session import BacktestSession, OrderRequest

from . import universe
from .dataset import LOCK, Dataset
from .strategy import OracleNetBrain

COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
INITIAL_CAPITAL = 100_000.0
CONTINUOUS_TRADE_FROM = "2018-01-01T00:00:00+00:00"
FORWARD_WARMUP_BARS = 2_000  # bars before the lock so trading opens warm at 2026-01-01
DEFAULT_REPORT_DIR = Path("research/agent_runs/system06")


def _moment(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _drive(session: BacktestSession, brain: OracleNetBrain, trade_from: str | None) -> int:
    """The pull loop with the warm-up gate the harness owns, not the brain.

    Every window serves history before `trade_from` so the signal table is warm;
    an order dated before it is withheld and counted, so a brain that tried to
    trade the warm-up is visible in the result rather than in a log line.
    """
    opens = _moment(trade_from)
    withheld = 0
    while True:
        tick = session.next_tick()
        if tick.get("done"):
            return withheld
        decision = brain.decide(tick)
        if decision.stop:
            session.stop(decision.stop)
            return withheld
        orders, note = decision.orders, decision.note
        moment = _moment(tick.get("timestamp"))
        if orders and opens is not None and moment is not None and moment < opens:
            withheld += len(orders)
            note = (f"{note} | " if note else "") + f"withheld {len(orders)}: opens {opens:%Y-%m-%d}"
            orders = []
        if orders or note:
            session.submit([OrderRequest.from_payload(o) for o in orders], note)


def run_window(
    bars_by_symbol: dict[str, list[Bar]],
    start: datetime,
    trade_from: str,
    end: datetime,
    signals: str,
    label: str,
    capital: float = INITIAL_CAPITAL,
    brain_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One measurement: one window, the same brain genome, one honest number."""
    brain = OracleNetBrain(signals=signals, trade_from=trade_from, **(brain_kwargs or {}))
    sliced = {
        symbol: [b for b in bars if start <= b.timestamp <= end]
        for symbol, bars in bars_by_symbol.items()
    }
    sliced = {symbol: bars for symbol, bars in sliced.items() if len(bars) >= 2}
    if not sliced:
        raise ValueError(f"{label}: no symbol has bars in [{start}, {end}]")

    run = BacktestRun(
        backtest_id=BacktestRun.fingerprint(
            "system06-oracle-net", brain.parameters(), {},
            BacktestRun.universe_digest(sliced),
            start.isoformat(), end.isoformat(), capital,
        ),
        label=f"system06-{label}",
        created_at=utc_now(),
        initial_capital=capital,
        strategy_family="system06-oracle-net",
        strategy_params=brain.parameters(),
        policy={},
        universe_size=len(sliced),
        window_start=start.isoformat(),
        window_end=end.isoformat(),
    )
    session = BacktestSession(
        run=run, bars_by_symbol=sliced, costs=CostModel(COMMISSION_BPS, SLIPPAGE_BPS)
    )
    withheld = _drive(session, brain, trade_from)
    summary = session.summary()
    summary["warmup_orders_withheld"] = withheld
    summary["window"] = {"start": start.isoformat(), "trade_from": trade_from, "end": end.isoformat()}
    # A downsampled equity curve so the monitor can draw the path, not just the
    # endpoints. Capped to ~500 points — enough to read the shape, small enough
    # to keep the report a report.
    curve = session.equity_curve
    step = max(1, len(curve) // 500)
    summary["equity"] = [
        {"timestamp": p["timestamp"], "equity": p["equity"], "cash": p["cash"],
         "open_positions": p.get("open_positions", 0), "active": p.get("active", False)}
        for p in curve[::step]
    ]
    return summary


# A recent, pre-2026 slice used to SELECT parameters honestly. The full continuous
# account back to 2018 spans the 2018 and 2022 crashes, so almost any long book
# eventually trips the 25% mandate there — a poor discriminator. The last ~18
# months before the lock is recent-regime-relevant and still never touches 2026.
VALIDATION_WARMUP_FROM = "2024-01-01T00:00:00+00:00"
VALIDATION_TRADE_FROM = "2024-07-01T00:00:00+00:00"


def training(dataset: Dataset, signals: str, trade_from: str = CONTINUOUS_TRADE_FROM,
             brain_kwargs: dict[str, Any] | None = None) -> dict:
    """One account from `trade_from` to the lock — the fitted era, continuous."""
    bars = dataset.research()
    stamps = sorted({b.timestamp for series in bars.values() for b in series})
    return run_window(
        bars, stamps[0], trade_from, stamps[-1], signals, "training", brain_kwargs=brain_kwargs
    )


def validation(dataset: Dataset, signals: str,
               brain_kwargs: dict[str, Any] | None = None) -> dict:
    """Recent pre-2026 portfolio backtest — the honest selection signal, 2026-free."""
    bars = dataset.research()
    stamps = sorted({b.timestamp for series in bars.values() for b in series})
    start = _moment(VALIDATION_WARMUP_FROM) or stamps[0]
    return run_window(
        bars, start, VALIDATION_TRADE_FROM, stamps[-1], signals, "validation",
        brain_kwargs=brain_kwargs,
    )


# ---- calendar-year evaluation -------------------------------------------------
# The law the operator set: an algorithm must be judged the way money is actually
# invested — Jan 1 to Dec 31, every single year. So each calendar year is its own
# INDEPENDENT account: fresh capital on Jan 1, its own 25% peak-to-trough mandate,
# warmed by ~2000 bars of prior history so the signal table is live at the open.
# "Positive every year" is then literal: every independent year finishes up.
CALENDAR_WARMUP_BARS = 2_000


def _year_start(stamps: list[datetime], jan1: datetime) -> datetime:
    before = [s for s in stamps if s < jan1]
    if len(before) >= CALENDAR_WARMUP_BARS:
        return before[-CALENDAR_WARMUP_BARS]
    return before[0] if before else jan1


def year_window(bars_by_symbol: dict[str, list[Bar]], stamps: list[datetime], year: int,
                signals: str, brain_kwargs: dict[str, Any] | None = None,
                min_bars: int = 100) -> dict | None:
    """One independent calendar-year account (Jan 1 -> Dec 31), fresh capital,
    own 25% mandate, warmed by prior history. None if the year has no data."""
    jan1 = datetime(year, 1, 1, tzinfo=timezone.utc)
    dec31 = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    if sum(1 for s in stamps if jan1 <= s <= dec31) < min_bars:
        return None
    start = _year_start(stamps, jan1)
    return run_window(bars_by_symbol, start, jan1.isoformat(), dec31, signals,
                      f"y{year}", brain_kwargs=brain_kwargs)


PER_YEAR_KEYS = ("return_pct", "max_drawdown", "trades", "average_exposure", "status", "stop_reason")


def per_year(bars_by_symbol: dict[str, list[Bar]], stamps: list[datetime], years,
             signals: str, brain_kwargs: dict[str, Any] | None = None,
             on_year=None, keep_equity: bool = False) -> dict[int, dict]:
    """Independent per-calendar-year backtests over `years`. One bad year drops out.

    `on_year(year, result, index, total)` is called before each year starts (result
    None) and again after it finishes (result dict), so a supervisor can publish live
    progress. `keep_equity` retains the downsampled equity curve for charting."""
    out: dict[int, dict] = {}
    years = list(years)
    keys = PER_YEAR_KEYS + (("equity",) if keep_equity else ())
    for i, y in enumerate(years):
        if on_year:
            on_year(y, None, i, len(years))
        try:
            r = year_window(bars_by_symbol, stamps, y, signals, brain_kwargs=brain_kwargs)
        except Exception as exc:  # noqa: BLE001
            out[y] = {"error": str(exc)}
            if on_year:
                on_year(y, out[y], i, len(years))
            continue
        if r is not None:
            out[y] = {k: r.get(k) for k in keys}
        if on_year:
            on_year(y, out.get(y), i, len(years))
    return out


def forward(dataset: Dataset, signals: str, brain_kwargs: dict[str, Any] | None = None) -> dict:
    """The sealed 2026 window, warmed by history before the lock. Same genome."""
    bars = dataset.combined()
    stamps = sorted({b.timestamp for series in bars.values() for b in series})
    lock = dataset.lock
    after = [s for s in stamps if s >= lock]
    before = [s for s in stamps if s < lock]
    if not after:
        raise ValueError("no bars at or after the lock: nothing to forward-test")
    if len(before) < FORWARD_WARMUP_BARS:
        raise ValueError(f"only {len(before)} bars before the lock; {FORWARD_WARMUP_BARS} needed")
    start = before[-FORWARD_WARMUP_BARS]
    return run_window(bars, start, lock.isoformat(), after[-1], signals, "forward", brain_kwargs=brain_kwargs)


def _print(result: dict[str, Any]) -> None:
    w = result["window"]
    print(
        f"{result['label']:<22} {w['trade_from'][:10]} -> {w['end'][:10]}\n"
        f"  return {result['return_pct']:+.2%}   maxDD {result['max_drawdown']:.2%}   "
        f"trades {result['trades']}   exposure {result['average_exposure']:.1%}   "
        f"status {result['status']}"
    )
    if result.get("stop_reason"):
        print(f"  stopped: {result['stop_reason']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phase", choices=("training", "forward", "both"), default="both")
    parser.add_argument("--symbols", default=None, help="comma list; default = the saved universe")
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--signals", default="research/system06/signals.npz")
    parser.add_argument("--trade-from", default=CONTINUOUS_TRADE_FROM)
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    args = parser.parse_args(argv)

    symbols = [s for s in args.symbols.split(",") if s] if args.symbols else universe.load()
    dataset = Dataset(args.data_root, symbols=symbols, interval=args.interval)
    report: dict[str, Any] = {"family": "system06-oracle-net", "symbols": symbols,
                              "interval": args.interval, "generated_at": utc_now()}

    if args.phase in ("training", "both"):
        result = training(dataset, args.signals, trade_from=args.trade_from)
        report["training"] = result
        _print(result)

    if args.phase in ("forward", "both"):
        result = forward(dataset, args.signals)
        report["forward"] = result
        _print(result)

    directory = Path(args.report_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{utc_now()[:19].replace(':', '')}-{args.phase}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nreport: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
