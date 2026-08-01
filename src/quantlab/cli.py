from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .data import BinanceProvider, DataManager
from .loop import ResearchDirector
from .autonomous import run_daemon
from .registry import strategy_registry
from . import service


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="quantlab", description="Autonomous crypto research laboratory"
    )
    root.add_argument("--config", default="config/default.json")
    commands = root.add_subparsers(dest="command", required=True)
    loop = commands.add_parser("loop", help="run finite, checkpointed research cycles")
    loop.add_argument("--max-cycles", type=int, default=1)
    loop.add_argument("--max-seconds", type=float)
    commands.add_parser("status", help="show persistent loop state")
    registry = commands.add_parser(
        "registry",
        help="audit every strategy's final equity, the forward runs and the champion",
    )
    registry.add_argument("--top", type=int, default=15)
    commands.add_parser(
        "daemon", help="run research, development agent and dashboard continuously"
    )
    service_parser = commands.add_parser(
        "service", help="manage the persistent macOS launch agent"
    )
    service_parser.add_argument(
        "action", choices=["install", "start", "stop", "status"]
    )
    download = commands.add_parser(
        "download", help="download public Binance spot klines"
    )
    download.add_argument("symbol")
    download.add_argument("--interval", default="1d")
    download.add_argument("--start", required=True)
    download.add_argument("--end", required=True)
    return root


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    settings = Settings.load(args.config)
    if args.command == "loop":
        reports = ResearchDirector(settings).run(args.max_cycles, args.max_seconds)
        print(
            json.dumps({"completed_cycles": len(reports), "reports": reports}, indent=2)
        )
    elif args.command == "status":
        print(json.dumps(ResearchDirector(settings).status(), indent=2, sort_keys=True))
    elif args.command == "registry":
        print(json.dumps(strategy_registry(settings, args.top), indent=2))
    elif args.command == "daemon":
        run_daemon(settings)
    elif args.command == "service":
        workspace = Path.cwd().resolve()
        config = Path(args.config).resolve()
        if args.action == "install":
            print(
                json.dumps(
                    {
                        "installed": str(service.install(workspace, config)),
                        "dashboard": f"http://{settings.autonomous.get('dashboard_host', '127.0.0.1')}:{settings.autonomous.get('dashboard_port', 8765)}",
                    },
                    indent=2,
                )
            )
        elif args.action == "start":
            service.start()
            print("service started")
        elif args.action == "stop":
            service.stop()
            print("service stopped; launchd remains installed")
        else:
            running, detail = service.status()
            print(
                json.dumps(
                    {"installed_and_running": running, "detail": detail[-4000:]},
                    indent=2,
                )
            )
    elif args.command == "download":
        manager = DataManager(settings.data_root, settings.splits["future_lock_start"])
        start, end = _date(args.start), _date(args.end)
        manager.validate_window(start, end)
        bars = BinanceProvider().bars(args.symbol, args.interval, start, end)
        audit = manager.audit(bars, args.interval, start, end)
        path = manager.save_csv(
            bars, "binance", args.symbol.upper(), args.interval, audit
        )
        print(
            json.dumps(
                {
                    "bars": len(bars),
                    "path": str(path),
                    "manifest": str(path.with_suffix(".manifest.json")),
                    "dataset_version": manager.version(
                        bars, "binance", args.symbol.upper(), args.interval
                    ),
                    "audit_passed": audit.passed,
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
