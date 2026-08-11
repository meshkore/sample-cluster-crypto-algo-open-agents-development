"""Re-publish finished runs so the public archive carries their regime.

The public mirror shows a grey, uncoloured equity line for every run recorded
before today, and the reason is a neat trap. `_publish` sends only decisions
that TRADED -- the right filter for an orders table -- and under the old brain a
bar that traded was exactly the bar that got NO note. So every decision that
reached the edge had an empty note, and the regime label, which travels in the
note, never left this machine.

The data is not lost. Run 9e9b0b87 has 83 decisions on the mirror with zero
notes between them, and 1,673 decisions locally of which 1,590 carry a label.
This walks the local database and re-publishes each run with its regime
timeline attached, so the archive colours itself.

It sends the same payload shape `_publish` sends, from the same code path, so
there is no second contract to keep in sync.

    python3 orchestrator-manager/scripts/backfill_regimes.py            # dry run
    python3 orchestrator-manager/scripts/backfill_regimes.py --publish
    python3 orchestrator-manager/scripts/backfill_regimes.py --publish --limit 20
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from quantlab_manager.config import Settings
from quantlab_manager.orchestration import Orchestrator
from quantlab_manager.sessions import open_database, regime_timeline

RUNTIME = Path.home() / "Library/Application Support/QuantLab"


def market_cycle():
    """The global trend, computed once from the archive.

    THE INSIGHT THAT MAKES THIS CHEAP: the global trend is a property of the
    MARKET, not of a backtest. Every run over the same calendar sits under the
    same cycle, so it does not have to be recovered from each run's own
    decisions -- it can be dated once and handed to all of them.

    That matters because the archive cannot be repaired any other way. Runs
    recorded before the cycle existed have notes carrying only the middle
    level, and no amount of re-reading them will produce a label that was never
    computed. Dating the composite from the candles gives every one of them the
    same six clean phases the newest run has.

    Imported and not reimplemented: this is `CycleDetector` at its shipped
    defaults, driven over the broad composite the detector itself would build.
    """
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from market_shootout import composite, load_all, turnover_averages
    from quantlab_trading.regime import CycleDetector, MarketRegime

    market = load_all()
    stamps = sorted({s for series in market.values() for s in series})
    level = composite(market, stamps, "equal", turnover_averages(market))

    detector = CycleDetector()
    out, previous = [], None
    for stamp, value in zip(stamps, level):
        label = detector.observe(value)
        if label is MarketRegime.UNKNOWN or label is previous:
            continue
        out.append({"timestamp": stamp.isoformat(), "label": label.value})
        previous = label
    return out


def main() -> int:
    publish = "--publish" in sys.argv
    limit = 200
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    settings = Settings.load(RUNTIME / "orchestrator-manager/config/default.json")
    store = open_database(RUNTIME / settings.database_path)

    mirror = (settings.autonomous.get("public_mirror") or {}) if publish else {}
    token = os.environ.get(mirror.get("token_env") or "", "")
    if publish and not (mirror.get("url") and token):
        print(
            "refusing to publish without a mirror url and token.\n"
            f"  export {mirror.get('token_env') or 'QUANTLAB_PUBLIC_MIRROR_TOKEN'}=…",
            file=sys.stderr,
        )
        return 2

    lab = Orchestrator(
        database=RUNTIME / settings.database_path,
        indicators=RUNTIME / settings.data_root / "indicators",
        mirror_url=mirror.get("url"),
        mirror_token=token or None,
    )

    print("dating the global cycle from the archive…", flush=True)
    cycle = market_cycle()
    print(
        f"  {len(cycle)} phase changes · "
        f"{cycle[0]['timestamp'][:10]} → {cycle[-1]['timestamp'][:10]}"
    )
    for entry in cycle:
        print(f"    {entry['timestamp'][:10]}  {entry['label']}")

    runs = store.runs(limit=limit)
    print(f"{len(runs)} runs on record · {'PUBLISHING' if publish else 'dry run'}\n")
    print(f"  {'run':<34} {'decisions':>10} {'labelled':>9} {'changes':>8}")

    sent = skipped = 0
    for run in runs:
        backtest_id = run["backtest_id"]
        decisions = store.decisions(backtest_id, limit=20_000)
        # The GLOBAL cycle wins over whatever this run's own notes carry. Runs
        # recorded before the cycle existed have only the middle level in their
        # notes -- 74 phases of it, which is the churn the operator objected to
        # -- and the middle level is not what the chart's "major trend" legend
        # is claiming to show.
        timeline = cycle or regime_timeline(decisions)
        labelled = sum(1 for d in decisions if (d.get("note") or "").strip())
        label = (run.get("label") or backtest_id)[:33]
        print(f"  {label:<34} {len(decisions):>10} {labelled:>9} {len(timeline):>8}")
        # A run with no labelled bar has nothing to add. Re-sending it would
        # spend a request to publish the same grey line again.
        if not timeline:
            skipped += 1
            continue
        if publish:
            lab._publish(
                backtest_id,
                run,
                store.equity(backtest_id),
                store.orders(backtest_id, limit=2000),
                decisions,
                store.trades(backtest_id, limit=2000),
                regimes=timeline,
            )
            if lab.last_publish_error:
                print(f"      failed: {lab.last_publish_error}")
            else:
                sent += 1

    print(f"\n  {sent} republished · {skipped} had no regime to add")
    if not publish:
        print("  dry run: nothing was sent. Add --publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
