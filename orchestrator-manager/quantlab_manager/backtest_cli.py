"""A thin human window onto runs that agents launch. NOT the way work happens.

The real path is `quantlab_manager.orchestration.Orchestrator`: an agent writes
a brain, registers it, calls `launch(...)`, and the orchestrator starts the
backtester service, pulls the tape over HTTP and records the result. Nothing in
that path involves a terminal, because nothing about it should wait for a human
to type.

This module exists so a person can look at what the agents did -- `list` and
`show` -- and, for convenience, kick off a run by hand while debugging. `run`
here drives the session in-process rather than through the service, which makes
it the wrong tool for anything that matters: it does not exercise the wire, so a
protocol bug would not show up. Prefer the Orchestrator.

The entry point a contributor reaches for first. It picks a brain from the
trading system, runs it over the universe, and writes everything under one
`backtest_id` so the run can be listed, inspected and eventually drawn.

    # run the reference brain over the whole daily universe
    python3 -m quantlab_manager.backtest_cli run --label my-first-run

    # a couple of symbols, a window, real costs
    python3 -m quantlab_manager.backtest_cli run \\
        --symbols BTCUSDT ETHUSDT --start 2022-01-01 --end 2025-12-31 \\
        --commission-bps 10 --slippage-bps 5 --label majors-2022

    python3 -m quantlab_manager.backtest_cli list
    python3 -m quantlab_manager.backtest_cli show <backtest_id>

The 2026 lock is enforced here rather than trusted: `--end` may not reach into
the forward window unless `--forward` is passed explicitly, because the cost of
opening it by accident is that it stops being evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import json
import sqlite3
import sys

from quantlab_backtester.backtest import CostModel
from quantlab_backtester.data import DataManager
from quantlab_backtester.ledger import BacktestRun
from quantlab_backtester.models import utc_now
from quantlab_trading.runner import MandateBrain

from .config import Settings
from .sessions import open_database, run_session

LOCK = datetime(2026, 1, 1, tzinfo=timezone.utc)

BRAINS = {
    "mandate": MandateBrain,
}


def _load_universe(
    settings: Settings, symbols: list[str] | None, start, end
) -> dict[str, list]:
    database = Path(settings.database_path)
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    wanted = set(symbols or [])
    out: dict[str, list] = {}
    try:
        rows = connection.execute(
            "SELECT symbol, research_path FROM asset_universe "
            "WHERE research_path IS NOT NULL ORDER BY symbol"
        ).fetchall()
    finally:
        connection.close()
    for row in rows:
        if wanted and row["symbol"] not in wanted:
            continue
        bars = [
            bar
            for bar in DataManager.load_csv(row["research_path"])
            if (start is None or bar.timestamp >= start)
            and (end is None or bar.timestamp <= end)
        ]
        if len(bars) >= 2:
            out[row["symbol"]] = bars
    missing = wanted - set(out)
    if missing:
        raise SystemExit(f"no data for: {', '.join(sorted(missing))}")
    if not out:
        raise SystemExit("the universe is empty for that window")
    return out


def command_run(args: argparse.Namespace) -> int:
    settings = Settings.load(args.config)
    start = (
        datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
        if args.start
        else None
    )
    end = (
        datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
        if args.end
        else None
    )

    if not args.forward:
        if end is None or end >= LOCK:
            # Historical optimisation ends 2025-12-31. Opening 2026 by accident
            # is not a small mistake -- it is the only untouched evidence the
            # project has, and it cannot be un-seen.
            end = min(end or LOCK, LOCK)
            print(
                f"note: window capped at the 2026 lock ({end.date()}); "
                f"pass --forward to open the sealed window deliberately"
            )

    bars = _load_universe(settings, args.symbols, start, end)
    brain_class = BRAINS.get(args.brain)
    if brain_class is None:
        raise SystemExit(f"unknown brain {args.brain!r}; available: {sorted(BRAINS)}")
    brain = brain_class()

    parameters = {
        key: value
        for key, value in vars(brain).items()
        if isinstance(value, (int, float, str, bool))
    }
    run = BacktestRun(
        backtest_id=BacktestRun.fingerprint(
            args.brain,
            parameters,
            {},
            BacktestRun.universe_digest(bars),
            start.isoformat() if start else None,
            end.isoformat() if end else None,
            args.capital,
        ),
        label=args.label or f"{args.brain}-{utc_now()[:19]}",
        created_at=utc_now(),
        initial_capital=args.capital,
        strategy_family=args.brain,
        strategy_params=parameters,
        policy={},
        universe_size=len(bars),
        window_start=start.isoformat() if start else None,
        window_end=end.isoformat() if end else None,
    )

    store = open_database(settings.database_path)
    print(f"backtest {run.backtest_id}  brain={args.brain}  assets={len(bars)}")

    shown = {"n": 0}

    def progress(tick: dict[str, Any]) -> None:
        shown["n"] += 1
        if shown["n"] % 200 == 0:
            clock = tick["clock"]
            print(
                f"  {clock['processed']:>5}/{clock['total']}  "
                f"equity {tick['account']['equity']:>12,.0f}  "
                f"positions {len(tick['account']['positions'])}",
                flush=True,
            )

    summary = run_session(
        brain,
        run,
        bars,
        store=store,
        costs=CostModel(args.commission_bps, args.slippage_bps),
        submitted_by=args.submitted_by,
        on_tick=progress,
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


def command_list(args: argparse.Namespace) -> int:
    settings = Settings.load(args.config)
    store = open_database(settings.database_path)
    runs = store.runs(limit=args.limit)
    if not runs:
        print("no backtests recorded yet")
        return 0
    print(f"{'backtest_id':<18}{'status':<10}{'label':<28}{'return':>10}{'trades':>8}")
    for row in runs:
        print(
            f"{row['backtest_id']:<18}{row['status']:<10}{(row['label'] or '')[:27]:<28}"
            f"{(row['return_pct'] or 0):>9.2%}{row['trades'] or 0:>8}"
        )
    return 0


def command_show(args: argparse.Namespace) -> int:
    settings = Settings.load(args.config)
    store = open_database(settings.database_path)
    run = store.run(args.backtest_id)
    if run is None:
        raise SystemExit(f"no backtest {args.backtest_id}")
    print(json.dumps(run, indent=2, default=str))
    orders = store.orders(args.backtest_id, limit=args.orders)
    print(f"\nfirst {len(orders)} orders")
    for order in orders:
        print(
            f"  {order['timestamp'][:10]}  {order['side']:<5}{order['symbol']:<14}"
            f"{order['notional']:>12,.2f}  {order['reason']}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="orchestrator-manager/config/default.json",
        type=Path,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="run a brain over the universe")
    run_parser.add_argument("--brain", default="mandate", choices=sorted(BRAINS))
    run_parser.add_argument("--label", default=None)
    run_parser.add_argument("--symbols", nargs="*", default=None)
    run_parser.add_argument("--start", default=None, help="YYYY-MM-DD")
    run_parser.add_argument("--end", default=None, help="YYYY-MM-DD")
    run_parser.add_argument("--capital", type=float, default=100_000.0)
    run_parser.add_argument("--commission-bps", type=float, default=10.0)
    run_parser.add_argument("--slippage-bps", type=float, default=5.0)
    run_parser.add_argument("--submitted-by", default="cli")
    run_parser.add_argument(
        "--forward",
        action="store_true",
        help="deliberately open the sealed 2026 window",
    )
    run_parser.set_defaults(func=command_run)

    list_parser = sub.add_parser("list", help="list recorded backtests")
    list_parser.add_argument("--limit", type=int, default=25)
    list_parser.set_defaults(func=command_list)

    show_parser = sub.add_parser("show", help="show one backtest")
    show_parser.add_argument("backtest_id")
    show_parser.add_argument("--orders", type=int, default=20)
    show_parser.set_defaults(func=command_show)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
