"""The laboratory's command line: start things, look at things. Never decide.

Work is launched by agents through `Orchestrator.launch`, not from a terminal,
so this is deliberately small. What is left is the handful of operations a
person genuinely performs by hand: bring the monitor up, download candles,
backfill indicators, and read what the agents did.

    python3 -m quantlab_manager monitor
    python3 -m quantlab_manager backfill
    python3 -m quantlab_manager download --symbols BTCUSDT ETHUSDT
    python3 -m quantlab_manager runs
    python3 -m quantlab_manager show <backtest_id>
    python3 -m quantlab_manager service install
"""

from __future__ import annotations

from pathlib import Path
import argparse
import json

from quantlab_backtester.data import BinanceProvider, DataManager

from . import service
from .backfill import backfill_universe
from .config import Settings
from .monitor_server import run_daemon
from .sessions import open_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantlab", description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("orchestrator-manager/config/default.json"),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    monitor = commands.add_parser("monitor", help="serve the monitor page and archive")
    monitor.add_argument("--host", default="127.0.0.1")
    monitor.add_argument("--port", type=int, default=None)

    backfill = commands.add_parser(
        "backfill", help="precompute indicator panels for the universe"
    )
    backfill.add_argument("--symbols", nargs="*", default=None)

    download = commands.add_parser("download", help="fetch candles from the exchange")
    download.add_argument("--symbols", nargs="+", required=True)
    download.add_argument("--interval", default="1d")

    runs = commands.add_parser("runs", help="list recorded backtests, newest first")
    runs.add_argument("--limit", type=int, default=30)

    show = commands.add_parser("show", help="summarise one backtest")
    show.add_argument("backtest_id")

    publish = commands.add_parser(
        "publish", help="push recorded runs to the public mirror"
    )
    publish.add_argument(
        "--all",
        action="store_true",
        help="republish every run, not only those the edge is missing",
    )
    publish.add_argument("--limit", type=int, default=200)

    loop_parser = commands.add_parser("loop", help="run the never-ending research loop")
    loop_parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="stop after N iterations (default: never)",
    )
    loop_parser.add_argument("--generations", type=int, default=5)
    loop_parser.add_argument("--population", type=int, default=14)
    loop_parser.add_argument(
        "--symbols",
        type=int,
        default=0,
        help="cap the candidate list at the N most-traded assets (0 = every "
        "asset we hold data for, which is the honest default)",
    )
    loop_parser.add_argument(
        "--no-cluster",
        action="store_true",
        help="do not post to or read from the MeshKore Wall",
    )

    service_parser = commands.add_parser(
        "service", help="install or remove the supervised monitor"
    )
    service_parser.add_argument(
        "action",
        choices=[
            "install",
            "install-loop",
            "uninstall",
            "uninstall-loop",
            "status",
        ],
        help="`install` supervises the monitor; `install-loop` supervises the "
        "research loop, which otherwise dies with the shell that started it",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.load(args.config)

    if args.command == "monitor":
        return run_daemon(settings, args.host, args.port)

    if args.command == "backfill":
        report = backfill_universe(settings, args.symbols)
        print(json.dumps(report, indent=2))
        return 0

    if args.command == "download":
        provider = BinanceProvider()
        manager = DataManager(provider, Path(settings.data_root))
        for symbol in args.symbols:
            path = manager.ensure(symbol, args.interval)
            print(f"{symbol:<12} {path}")
        return 0

    if args.command == "runs":
        store = open_database(settings.database_path)
        rows = store.runs(limit=args.limit)
        if not rows:
            print("no backtests recorded yet")
            return 0
        print(f"{'created':<20}{'label':<34}{'return':>10}{'trades':>8}  status  id")
        for row in rows:
            print(
                f"{str(row['created_at'])[:19]:<20}{str(row['label'])[:33]:<34}"
                f"{(row['return_pct'] or 0):>9.2%}{row['trades'] or 0:>8}"
                f"  {row['status']:<9}{row['backtest_id']}"
            )
        return 0

    if args.command == "show":
        store = open_database(settings.database_path)
        run = store.run(args.backtest_id)
        if run is None:
            print(f"no backtest {args.backtest_id}")
            return 1
        equity = store.equity(args.backtest_id)
        orders = store.orders(args.backtest_id)
        print(json.dumps(run, indent=2, default=str))
        print(f"\nequity points {len(equity)} · orders {len(orders)}")
        return 0

    if args.command == "publish":
        return run_publish(settings, args)

    if args.command == "loop":
        return run_loop(settings, args)

    if args.command == "service":
        return service.run(args.action, args.config)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())


def mirror_credentials(settings) -> tuple[dict, str]:
    """Where the public mirror is, and the token that may write to it.

    One function because the alternative cost a night of research. `Settings` is
    a frozen dataclass with an `autonomous` field and no `raw` one, and the loop
    read `settings.raw` behind a `hasattr` guard -- so it took the else branch
    every single time and started with no mirror configured. `_publish` returns
    at its first line when the URL is missing, silently and by design, because
    publication must never fail a backtest. The result was eighteen forward runs
    recorded locally, none published, and a public page that looked like a
    laboratory which had stopped at midnight. A guard around a name that does
    not exist is not defensive; it is a permanent no-op with a reassuring shape.
    """
    import os

    mirror = (settings.autonomous or {}).get("public_mirror", {}) or {}
    token = os.environ.get(mirror.get("token_env", "QUANTLAB_PUBLIC_MIRROR_TOKEN"), "")
    return mirror, token


def run_publish(settings, args) -> int:
    """Push recorded runs to the edge, for when the edge missed them.

    Publication is best effort inside a run: the local database is the record
    and a network blip is not a research event. That is the right trade, and it
    means the archive can silently fall behind -- so there has to be a way to
    catch it up that does not involve re-running the research.
    """
    from .orchestration import Orchestrator
    from .sessions import open_database

    mirror, token = mirror_credentials(settings)
    if not mirror.get("url") or not token:
        print("no public mirror configured (url or token missing)")
        return 1

    store = open_database(settings.database_path)
    lab = Orchestrator(
        database=Path(settings.database_path),
        indicators=Path(settings.data_root) / "indicators",
        mirror_url=mirror["url"],
        mirror_token=token,
    )
    known: set[str] = set()
    if not args.all:
        import urllib.request

        try:
            with urllib.request.urlopen(
                f"{mirror['url']}/api/backtests", timeout=20
            ) as response:
                index = json.loads(response.read() or b"{}")
            known = {
                str(row.get("backtest_id"))
                for row in (index.get("history") or []) + (index.get("live") or [])
            }
        except Exception as exc:  # noqa: BLE001 - fall back to republishing all
            print(f"could not read the edge index ({exc}); publishing everything")

    sent = failed = 0
    for row in reversed(store.runs(limit=args.limit)):
        backtest_id = row["backtest_id"]
        if backtest_id in known:
            continue
        lab._publish(
            backtest_id,
            store.run(backtest_id),
            store.equity(backtest_id),
            store.orders(backtest_id, limit=2000),
            store.decisions(backtest_id, limit=5000),
            store.trades(backtest_id, limit=2000),
        )
        if lab.last_publish_error:
            failed += 1
            print(f"  FAILED {backtest_id} {row['label']}: {lab.last_publish_error}")
        else:
            sent += 1
            print(f"  sent   {backtest_id} {row['label']}")
    print(f"{sent} published, {failed} failed, {len(known)} already on the edge")
    return 0 if not failed else 1


def run_loop(settings, args) -> int:
    """Start the loop. Two services on two ports, and that is the point.

    The fitting laboratory talks to a backtester started WITHOUT `--forward`, so
    it cannot be handed a bar past 2025-12-31 whatever a window says. The
    forward laboratory talks to one that can, and only `promote` uses it. Two
    processes is a heavier arrangement than one flag, and it is the reason the
    lock survives a careless edit.
    """
    import os
    import sqlite3

    from quantlab_trading.regime import REFERENCE_BASKET

    from .advisors import from_environment as advisors_from_environment
    from .advisors import explorer_from_environment, reviewer_from_environment
    from .cluster import from_environment as cluster_from_environment
    from .loop import ResearchLoop
    from .orchestration import Orchestrator
    from .sessions import open_database
    from .team import roster_markdown
    from .universes import select_universe

    repository = Path(os.environ.get("QUANTLAB_REPOSITORY_ROOT", Path.cwd()))
    database = Path(settings.database_path)
    indicators = database.parent.parent / "data" / "indicators"

    # Every asset we hold candles for is a CANDIDATE. Which of them may
    # actually be bought is decided per bar by the liquidity gate in
    # `quantlab_trading.universe`, from that bar's own trailing turnover, so a
    # coin enters the day it becomes liquid and leaves the day it stops being.
    #
    # This used to be `ORDER BY first_seen ASC LIMIT 50`, and every row in that
    # table carries the SAME first_seen -- one backfill, one timestamp. So the
    # sort decided nothing and SQLite returned rowid order, which is
    # alphabetical: sixty-six iterations were run on 0G, 1000CAT, 1INCH, AAVE
    # ... AXS. Half of those have under 400 bars and only one has any history
    # before 2019, which is why fold 1 returned +1% in every iteration ever
    # recorded -- there was nothing in it to trade.
    #
    # A cap is still expressible, and when given it ranks by turnover rather
    # than by name. It is not the default: 375 of our 386 symbols are in the
    # daily top 100 by turnover at some point in their life, so any fixed
    # shortlist drawn today would silently delete the assets that mattered in
    # their own era and call the survivors the universe.
    if args.symbols and args.symbols > 0:
        candidates = select_universe(settings, size=args.symbols)["symbols"]
    else:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        candidates = [
            row[0]
            for row in connection.execute(
                "SELECT symbol FROM asset_universe WHERE research_path IS NOT NULL"
            )
        ]
        connection.close()
    symbols = sorted(set(REFERENCE_BASKET) | set(candidates))

    # The deployment scope, pinned into every launch and reachable by no search.
    # Both numbers are the operator's, already in the config and until now read
    # by nothing on this path.
    deployment = {
        "minimum_daily_quote_volume": float(
            settings.portfolio.get("minimum_daily_quote_volume", 0.0)
        ),
        "tradeable_assets": int(settings.universe.get("maximum_assets", 0)),
    }

    mirror, token = mirror_credentials(settings)

    lab_fit = Orchestrator(database=database, indicators=indicators, port=8770)
    lab_forward = Orchestrator(
        database=database,
        indicators=indicators,
        port=8771,
        forward=True,
        mirror_url=mirror.get("url"),
        mirror_token=token or None,
    )
    proposer, critic = advisors_from_environment()
    # The local reviewer reads THIS working copy, so it is pointed at the
    # repository root rather than the runtime's data directory.
    reviewer = reviewer_from_environment()
    # The seat that goes and looks outside the repository, on exploration
    # turns only, and the seat that reviews the loop itself.
    explorer = explorer_from_environment()
    from .advisors import ClaudeCliAdvisor
    from .evolve import EVOLVE_SYSTEM

    reviewer_of_self = ClaudeCliAdvisor(system=EVOLVE_SYSTEM, timeout=600.0)
    if reviewer is not None:
        reviewer.repository = str(repository)
    cluster = cluster_from_environment(repository)
    cluster.enabled = cluster.enabled and not args.no_cluster

    loop = ResearchLoop(
        lab_fit=lab_fit,
        lab_forward=lab_forward,
        store=open_database(database),
        symbols=symbols,
        repository=repository,
        cluster=cluster if cluster.enabled else None,
        proposer=proposer,
        critic=critic,
        reviewer=reviewer,
        explorer=explorer,
        reviewer_of_self=reviewer_of_self,
        generations=args.generations,
        population=args.population,
        deployment=deployment,
        publish=lab_forward.publish_activity,
    )
    print(
        f"loop starting · {len(symbols)} candidate symbols · "
        f"buys gated at {deployment['minimum_daily_quote_volume']:,.0f} "
        f"turnover, top {deployment['tradeable_assets']} · "
        f"proposer {'on' if proposer.available else 'off'} · "
        f"critic {'on' if critic.available else 'off'} · "
        # Named, because a member that is silently absent looks exactly like a
        # member that had nothing to say. The reviewer spent weeks written,
        # rostered and unbuilt, and this line said nothing either way.
        f"reviewer {'on' if reviewer is not None and reviewer.available else 'off'} · "
        f"explorer {'on' if explorer is not None and explorer.available else 'off'} · "
        f"cluster {'on' if cluster.enabled else 'off'}",
        flush=True,
    )
    # WHICH state it resumed from, said out loud. A supervised loop that quietly
    # starts at iteration 1 because it read a path nobody expected would append
    # H-L001 over an id the ledger already holds, and the append-only record
    # would carry two different hypotheses under one name before anybody
    # noticed. The state file is the only thing standing between a restart and
    # a rewritten history, so a restart has to name it.
    print(
        f"resumed · iteration {loop.state.iteration} · "
        f"incumbent {loop.state.incumbent_forward} · "
        f"{len(loop.state.history)} history entries · {loop.state_path}",
        flush=True,
    )
    if cluster.enabled:
        cluster.post(
            "blackmac-quantlab-loop",
            "## The research loop is starting\n\n" + roster_markdown(),
        )
    try:
        loop.run_forever(maximum_iterations=args.iterations)
    finally:
        lab_fit.close()
        lab_forward.close()
    return 0
