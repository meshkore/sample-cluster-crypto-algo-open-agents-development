#!/usr/bin/env python3
"""Record an intraday run in the laboratory's database and publish it.

    python3 orchestrator-manager/scripts/publish_intraday.py \
        --phase training --brain intraday-momentum --set trend_ma_days=30 ...
    python3 orchestrator-manager/scripts/publish_intraday.py \
        --phase forward  --brain intraday-momentum --set trend_ma_days=30 ...

`quantlab_intraday.launch` measures a hypothesis; this puts the result where a
reader can see it. They are separate programs because the layering contract
says so: `trading-system/` may not import the lab, so nothing inside the
intraday package can open a database or reach the mirror. This script sits on
the manager's side of that wall, imports both, and is the only thing that does.

**Why the training half is ONE continuous run and not the eight blocks.**
Blocks answer "does the mechanism survive different eras" and that is what
chose the configuration. The monitor asks a different question -- what did this
strategy do over the years it was allowed to be fitted on, against what it did
in 2026 -- and a card can only carry one figure per era. So the published
training half is the house convention every loop run already follows: load from
the first bar of history, open trading on `--trade-from`, close on the lock.

**The pair is the point.** `pair_key` hashes the strategy family plus the
genome with `trade_from` removed, so two runs are two halves of one hypothesis
exactly when every other parameter matches. This script takes the same `--set`
flags for both phases and refuses to invent any, which is what makes that
match structural rather than remembered.

**The equity curve is thinned for publication only.** A 5-minute run over eight
years has ~880,000 points; the database keeps every one of them, and the mirror
is sent one point per day. Drawdown and return are computed from the full curve
before anything is thinned, so no published figure is affected -- only the
resolution of the line drawn under it.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for package in ("backtester", "trading-system", "orchestrator-manager"):
    sys.path.insert(0, str(ROOT / package))

from quantlab_intraday import launch  # noqa: E402
from quantlab_intraday.dataset import (  # noqa: E402
    DEFAULT_SYMBOLS,
    LOCK,
    IntradayDataset,
    Window,
)
from quantlab_manager.cli import mirror_credentials  # noqa: E402
from quantlab_manager.config import Settings  # noqa: E402
from quantlab_manager.orchestration import Orchestrator  # noqa: E402
from quantlab_manager.sessions import open_database  # noqa: E402

# The handle this work belongs to. `submitted_by` is what the monitor groups a
# job by, so a run submitted under a handle no heartbeat claims gets its own
# card -- which is correct here: this is a person at a terminal, not the loop.
SUBMITTED_BY = "blackmac-vcode-intraday"

# Where trading opens in the training half. The loop's own training runs open on
# 2018-01-01 over a history that starts 2017-08-17, and matching that is worth
# more than a few extra weeks of tape: it is the difference between a card a
# reader can compare with the ones beside it and one they cannot.
TRAINING_TRADE_FROM = "2018-01-01T00:00:00+00:00"

# Bars of history served ahead of the sealed window. The brain's longest memory
# is a 30-day moving average -- 8,640 bars at this resolution -- and a filter
# that is still warming refuses every entry and reports it as no signal, so the
# margin is deliberate rather than generous.
FORWARD_WARMUP_BARS = 40_000


def credentials(settings: Settings) -> tuple[dict[str, Any], str]:
    """Where the mirror is and what may write to it, env or file.

    `mirror_credentials` reads one environment variable, which the LaunchAgent
    sets and a terminal does not -- so a run driven by hand records perfectly
    and then declines to publish, having spent an hour computing the thing it
    is declining to publish. The two files below are the same ones
    `service.py` injects into that agent's environment, in the same order:
    the private copy first, then the one the operator deliberately keeps in the
    public tree (see `.meshkore/public/MIRROR_PUBLISH.md`).
    """
    mirror, token = mirror_credentials(settings)
    if token:
        return mirror, token
    for candidate in (
        ROOT / ".meshkore" / "credentials" / "public-mirror-token",
        ROOT / ".meshkore" / "public" / "mirror-publish",
    ):
        if candidate.exists():
            value = candidate.read_text().strip()
            if value:
                return mirror, value
    return mirror, ""


def publish(
    settings: Settings, store: Any, backtest_id: str, quiet: bool = False
) -> int:
    """Push one recorded run to the mirror. The database is already the record."""
    mirror, token = credentials(settings)
    if not mirror.get("url") or not token:
        # Not fatal to the research. The measurement is in the database; a
        # missing credential is a deployment fact rather than a result.
        print("no public mirror configured (url or token missing)")
        return 1
    stored = store.run(backtest_id)
    if stored is None:
        print(f"no such run: {backtest_id}")
        return 1
    lab = Orchestrator(
        database=ROOT / settings.database_path,
        indicators=ROOT / settings.data_root / "indicators",
        store=store,
        mirror_url=mirror["url"],
        mirror_token=token,
    )
    curve = thin_daily(store.equity(backtest_id))
    lab._publish(
        backtest_id,
        stored,
        curve,
        store.orders(backtest_id, limit=2000),
        store.decisions(backtest_id, limit=5000),
        store.trades(backtest_id, limit=2000),
    )
    if lab.last_publish_error:
        print(f"PUBLISH FAILED: {lab.last_publish_error}")
        return 1
    if not quiet:
        print(
            f'published {backtest_id} "{stored["label"]}" '
            f"({len(curve)} equity points) to {mirror['url']}"
        )
    return 0


def thin_daily(curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One point per UTC day, keeping the first and last of the whole curve."""
    if len(curve) <= 2:
        return list(curve)
    kept: list[dict[str, Any]] = [curve[0]]
    for point, following in zip(curve, curve[1:]):
        if str(point["timestamp"])[:10] != str(following["timestamp"])[:10]:
            kept.append(point)
    kept.append(curve[-1])
    return kept


def build_window(
    dataset: IntradayDataset,
    phase: str,
    trade_from: str,
    serve_from: str = "",
) -> tuple[dict[str, Any], Window]:
    """The tape to serve and when trading opens on it, for one phase."""
    if phase == "training":
        bars = dataset.research()
        stamps = IntradayDataset.timeline(bars)
        if serve_from:
            first = datetime.fromisoformat(serve_from)
            stamps = [stamp for stamp in stamps if stamp >= first]
        opens = datetime.fromisoformat(trade_from)
        tradeable = [stamp for stamp in stamps if stamp >= opens]
        if not tradeable:
            raise SystemExit(f"no bars at or after {trade_from}")
        return bars, Window(
            index=0,
            start=stamps[0],
            trade_from=tradeable[0],
            end=stamps[-1],
            label="training",
        )

    bars = dataset.combined()
    window = IntradayDataset.forward_window(
        bars, dataset.lock, warmup_bars=FORWARD_WARMUP_BARS
    )
    return bars, window


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phase", choices=("training", "forward"))
    parser.add_argument(
        "--republish",
        default="",
        metavar="BACKTEST_ID",
        help="publish a run already in the database and exit. A measurement is "
        "not re-run because a token was missing.",
    )
    parser.add_argument("--brain", default="intraday-momentum")
    parser.add_argument(
        "--brain-module",
        default="",
        help="import this module before building the brain, so a strategy that "
        "lives outside the built-in packages registers itself. Generated "
        "systems live in `quantlab_systemNN.strategy` and are unknown to the "
        "registry until something imports them; without this the publisher "
        "reports 'no brain named ...' for code that is sitting right there.",
    )
    parser.add_argument("--label", default="")
    parser.add_argument("--submitted-by", default=SUBMITTED_BY)
    parser.add_argument("--trade-from", default=TRAINING_TRADE_FROM)
    parser.add_argument(
        "--serve-from",
        default="",
        help="cut the front of the served training tape. For a smoke test of "
        "this script; a published training run serves the whole history.",
    )
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--data-root", default=str(ROOT / "backtester" / "data"))
    parser.add_argument(
        "--config",
        default=str(ROOT / "orchestrator-manager" / "config" / "default.json"),
    )
    parser.add_argument("--capital", type=float, default=launch.INITIAL_CAPITAL)
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="record locally and skip the mirror, for a smoke test",
    )
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    args = parser.parse_args(argv)

    settings = Settings.load(args.config)
    if args.republish:
        return publish(
            settings, open_database(ROOT / settings.database_path), args.republish
        )
    if not args.phase:
        parser.error("--phase is required unless --republish is given")

    parameters: dict[str, Any] = {}
    for item in args.set:
        key, _, raw = item.partition("=")
        parameters[key.strip()] = launch._coerce(raw.strip())

    symbols = [s for s in args.symbols.split(",") if s] or list(DEFAULT_SYMBOLS)
    dataset = IntradayDataset(args.data_root, LOCK, symbols, interval=args.interval)
    parameters.setdefault("bars_per_day", dataset.bars_per_day)

    print(f"loading {args.phase} tape ...", flush=True)
    bars, window = build_window(dataset, args.phase, args.trade_from, args.serve_from)
    print(
        f"{window.label}: serve {window.start:%Y-%m-%d} .. {window.end:%Y-%m-%d}, "
        f"trade from {window.trade_from:%Y-%m-%d}",
        flush=True,
    )

    session, brain = launch.build_session(
        bars,
        window,
        parameters,
        capital=args.capital,
        store=dataset.store_for(window),
        brain_name=args.brain,
    )
    # The label is the card's name; the id is a fingerprint of the genome and
    # the window, so two phases can never collide and re-running one replaces
    # itself rather than accumulating near-duplicates. `BacktestRun` is frozen
    # -- a run's identity is not editable once it exists -- so this replaces it
    # rather than renaming it, before the session has traded anything.
    session.run = replace(session.run, label=args.label or f"{args.brain}-{args.phase}")

    store = open_database(ROOT / settings.database_path)
    store.open_run(session.run, submitted_by=args.submitted_by)
    print(
        f"running {session.run.backtest_id} over {len(session.timeline):,} bars ...",
        flush=True,
    )

    launch._drive(session, brain)
    summary = launch.measure(session, brain, window, capital=args.capital)

    # The narration, thinned to the bars that did something. This brain returns
    # a note on every bar it sees -- which is the right behaviour, and at five
    # minutes over eight years it is 880,000 rows describing about 150 trades.
    # Both the database and the monitor keep the ones that traded; the rest say
    # "no signal" and are reconstructible from the tape at any time.
    narration = len(session.decisions)
    session.decisions = [
        decision
        for decision in session.decisions
        if decision.get("orders") or decision.get("rejected")
    ]
    print(f"decisions: {len(session.decisions):,} kept of {narration:,}")
    store.complete_session(session)
    stored = store.run(session.run.backtest_id)

    detail = summary["trades_detail"]
    print(
        f"\n{session.run.label}: {summary['return_pct']:.2%} "
        f"(pre-cost {detail['pre_cost_return_pct']:.2%}, toll "
        f"{detail['toll_pct_of_capital']:.1%}), maxDD {summary['max_drawdown']:.2%}, "
        f"{summary['trades']} trades, status {summary['status']}"
    )
    print(f"era {stored['era']}  pair_key {stored['pair_key']}")

    if args.no_publish:
        print("not published (--no-publish)")
        return 0

    return publish(settings, store, session.run.backtest_id)


if __name__ == "__main__":
    raise SystemExit(main())
