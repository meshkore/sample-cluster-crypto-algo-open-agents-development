"""Train and walk-forward the ML system on the research era. One command.

    python3 -m quantlab_ml.train --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT

Nothing here can reach 2026: the bars come from `IntradayDataset.research()`,
which loads through `DataManager`, which refuses post-lock data outright. The
sealed window is opened by the brain through the ordinary harness, once, after a
configuration has been fixed on what this prints.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


from quantlab_intraday.dataset import DEFAULT_SYMBOLS, LOCK, IntradayDataset

from . import dataset as ml_dataset
from .labels import Barriers
from .model import evaluate

REPORTS = Path("research/agent_runs/ml")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--target", type=float, default=2.0)
    parser.add_argument("--stop", type=float, default=1.0)
    parser.add_argument("--horizon", type=int, default=864)
    parser.add_argument("--folds", type=int, default=6)
    parser.add_argument("--embargo", type=int, default=864)
    parser.add_argument("--minimum-train", type=int, default=50_000)
    parser.add_argument(
        "--margin",
        type=float,
        default=0.0,
        help="expected net return a trade must clear before it is taken. The "
        "cost-aware filter: 0.0 already demands the toll be covered, because "
        "the round trip is subtracted inside the expectation.",
    )
    parser.add_argument("--max-bars", type=int, default=0, help="0 = the whole era")
    parser.add_argument(
        "--cache",
        default="research/agent_runs/cache",
        help="directory for the cached observation table. Building it over eight "
        "years of five-minute bars is minutes of arithmetic that does not change "
        "between experiments. Pass an empty string to rebuild every time.",
    )
    args = parser.parse_args(argv)

    symbols = [s for s in args.symbols.split(",") if s]
    data = IntradayDataset(args.data_root, LOCK, symbols, interval=args.interval)
    print(
        f"loading {len(symbols)} symbols of {args.interval} research tape ...",
        flush=True,
    )
    bars = data.research()
    if args.max_bars:
        bars = {s: b[-args.max_bars :] for s, b in bars.items()}
    print({s: len(b) for s, b in bars.items()}, flush=True)

    barriers = Barriers(args.target, args.stop, args.horizon)
    print("building features and triple-barrier labels ...", flush=True)
    observations = ml_dataset.build(
        bars, barriers, store=data.indicators, cache=args.cache or None
    )
    print(json.dumps(observations.document(), indent=1, default=str), flush=True)

    # One shared implementation, aligned ROW BY ROW. This used to be built here by
    # concatenating one array per symbol, which was correct only while the
    # observation table happened to be symbol-major; the table is now sorted by
    # time and that construction would hand every row another row's volatility.
    sigma = ml_dataset.barrier_sigma(observations, bars, args.horizon)

    print(
        f"\nwalk-forward: {args.folds} folds, embargo {args.embargo} bars ...",
        flush=True,
    )
    result = evaluate(
        observations,
        sigma,
        margin=args.margin,
        folds=args.folds,
        embargo=args.embargo,
        minimum_train=args.minimum_train,
    )

    header = (
        f"{'fold':>5}{'train':>10}{'test':>9}{'taken':>8}{'take%':>7}"
        f"{'net/trade':>11}{'t*':>7}{'indep':>7}{'purged':>8}"
    )
    print("\n" + header)
    print("-" * len(header))
    for fold in result.folds:
        print(
            f"{fold.fold:>5}{fold.train_rows:>10,}{fold.test_rows:>9,}{fold.taken:>8,}"
            f"{fold.taken / max(fold.test_rows, 1):>7.1%}{fold.mean_net_taken:>11.3%}"
            f"{fold.t_star:>7.2f}{fold.independent:>7,}{fold.purged:>8,}"
        )
    print("\n" + json.dumps(result.summary(), indent=1))
    print("\ntop features by gain:")
    for name, gain in result.importance[:15]:
        print(f"  {gain:>7.4f}  {name}")

    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    path = REPORTS / f"{stamp}-walkforward.json"
    path.write_text(
        json.dumps(
            {
                "observations": observations.document(),
                "folds": [f.document() for f in result.folds],
                "summary": result.summary(),
                "importance": result.importance,
                "arguments": vars(args),
            },
            indent=2,
            default=str,
        )
    )
    print(f"\nreport: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
