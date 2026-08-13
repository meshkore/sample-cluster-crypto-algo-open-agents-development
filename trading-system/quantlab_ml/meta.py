"""The meta-label: a verdict on each of the champion's entries, precomputed.

    python3 -m quantlab_ml.meta --out research/agent_runs/meta/itsm-h6.json

**What this is.** Lopez de Prado's meta-labelling (AFML ch. 3) splits a strategy
in two: a PRIMARY model decides the side, a SECONDARY model decides the size,
including zero. The primary here is the incumbent champion's rule -- at 06:00
UTC, if the day is already up 1.5%, buy -- and this file fits the secondary.
Published lifts on the technique are precision 0.48 -> 0.54 on an equity
strategy; the reason it is the right shape for THIS laboratory is different and
arithmetic. Every idea tried so far raised the trade count, and at a 30 bps round
trip that is a guaranteed cost against an uncertain gain: generation 4 traded 65
times, paid 4.9% of capital in toll, and its gross was -0.87%. A filter is the
only change that can raise the return and LOWER the bill at the same time.

**Why a table of verdicts rather than a model the brain calls.** The features are
46 columns built by `dataset.build` -- scale-free indicators, calendar, session
shape, and cross-sectional ranks that need every symbol on a shared clock. A
brain recomputing those live would be a second implementation of the same
arithmetic, and the day the two drift the model is fed garbage while every metric
still reads normally. So the verdicts are computed HERE, by the same call that
trained the model, and the brain does a lookup. There is no second
implementation to keep in step.

**The honesty of the research half is the whole difficulty.** A model fitted on
2018-2025 and then used to trade 2018-2025 knows the answers, and the training
card would be a fiction. So research-era verdicts come from the purged
walk-forward: the verdict on a bar is issued by a fold model whose training set
ended before that bar, with overlapping labels purged and an embargo band
dropped. Only the sealed 2026 rows are scored by the final model, which is fitted
on the research era and has never seen them. A bar with no fold that legitimately
covers it -- everything before the first test block -- gets NO verdict, and the
brain treats a missing verdict as a refusal rather than as permission.

**Candidates only.** The primary fires at one bar per symbol per day, so the
table has ~16,000 rows instead of 3,970,404. That is not an optimisation: it is
what lets the whole thing be a JSON file an operator can read.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from .dataset import barrier_sigma
from .labels import Barriers
from .model import CLASSES, build_classifier, expected_net
from .splits import purged_walk_forward

# The champion's trigger, so the candidate set is exactly the bars its rule can
# fire on. Kept here as data rather than imported: this file must be able to
# describe a candidate set for a primary that is not the champion.
ITSM_HOUR = 6
ITSM_MINUTE = 0


@dataclass(frozen=True)
class Verdict:
    """One row of the table the brain reads."""

    symbol: str
    timestamp: str
    value: float  # expected net return, already net of the round trip
    source: str  # "fold-3" or "final" -- which model issued it

    def document(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "value": round(self.value, 8),
            "source": self.source,
        }


def candidates(
    timestamps: np.ndarray, hour: int = ITSM_HOUR, minute: int = ITSM_MINUTE
) -> np.ndarray:
    """Boolean mask of the bars the primary rule is allowed to fire on.

    The threshold itself is deliberately NOT applied. The filter is asked about
    every bar at the trigger hour, so the same table serves a primary with a
    different threshold, and so a verdict can never be missing for a bar the
    primary decided to take.
    """
    out = np.zeros(len(timestamps), dtype=bool)
    for i, stamp in enumerate(timestamps):
        moment = stamp if isinstance(stamp, datetime) else None
        if moment is None:
            moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        out[i] = moment.hour == hour and moment.minute == minute
    return out


def _widen(model: Any, X: np.ndarray, encode: dict[int, int]) -> np.ndarray:
    """Probabilities back in the fixed CLASSES order, zeros for absent classes."""
    narrow = model.predict_proba(X)
    out = np.zeros((len(narrow), len(CLASSES)))
    for label, column in encode.items():
        out[:, CLASSES.index(label)] = narrow[:, column]
    return out


def _fit(X: np.ndarray, y: np.ndarray, seed: int, **kwargs: Any):
    """One classifier, with the per-fold label encoding XGBoost insists on."""
    present = sorted({int(v) for v in y})
    encode = {label: i for i, label in enumerate(present)}
    model = build_classifier(seed=seed, **kwargs)
    model.fit(X, np.array([encode[int(v)] for v in y]))
    return model, encode


def build_table(
    research: Any,
    research_sigma: np.ndarray,
    forward: Any | None = None,
    forward_sigma: np.ndarray | None = None,
    folds: int = 6,
    embargo: int = 864,
    minimum_train: int = 200_000,
    seed: int = 42,
    **model_kwargs: Any,
) -> tuple[list[Verdict], dict[str, Any]]:
    """Verdicts for every candidate bar, and the documentation of how.

    `research` and `forward` are observation tables ALREADY restricted to the
    candidate bars. The walk-forward is computed over the restricted table on
    purpose: the folds then tile the candidates evenly, so every era of the
    research half gets an out-of-sample verdict from a model of a comparable
    size. Splitting on the full table and subsetting afterwards would leave the
    early folds with a handful of candidates each.
    """
    barriers = research.meta.get("barriers", {})
    target = float(barriers.get("target", 2.0))
    stop = float(barriers.get("stop", 1.0))
    round_trip = float(research.meta.get("round_trip", 0.003))

    verdicts: list[Verdict] = []
    covered = 0
    splits = purged_walk_forward(
        research.ends_at, folds=folds, embargo=embargo, minimum_train=minimum_train
    )
    for fold in splits:
        model, encode = _fit(
            research.X[fold.train], research.y[fold.train], seed, **model_kwargs
        )
        probabilities = _widen(model, research.X[fold.test], encode)
        value = expected_net(
            probabilities, research_sigma[fold.test], target, stop, round_trip
        )
        for offset, row in enumerate(fold.test):
            verdicts.append(
                Verdict(
                    symbol=str(research.symbols[row]),
                    timestamp=str(research.timestamps[row]),
                    value=float(value[offset]),
                    source=f"fold-{fold.index}",
                )
            )
        covered += len(fold.test)

    # The final model: the whole research era, nothing after the lock. It is the
    # only model that may speak about 2026, and it may not speak about anything
    # else -- every research row already has an out-of-sample verdict above.
    final, encode = _fit(research.X, research.y, seed, **model_kwargs)
    if forward is not None and forward_sigma is not None and len(forward.y):
        probabilities = _widen(final, forward.X, encode)
        value = expected_net(probabilities, forward_sigma, target, stop, round_trip)
        for row in range(len(forward.y)):
            verdicts.append(
                Verdict(
                    symbol=str(forward.symbols[row]),
                    timestamp=str(forward.timestamps[row]),
                    value=float(value[row]),
                    source="final",
                )
            )

    document = {
        "primary": {"hour": ITSM_HOUR, "minute": ITSM_MINUTE},
        "barriers": {"target": target, "stop": stop},
        "round_trip": round_trip,
        "features": len(research.names),
        "feature_names": list(research.names),
        "research_candidates": int(len(research.y)),
        "research_covered": covered,
        "research_uncovered": int(len(research.y) - covered),
        "forward_candidates": int(len(forward.y)) if forward is not None else 0,
        "folds": [fold.document() for fold in splits],
        "verdicts": len(verdicts),
    }
    return verdicts, document


def restrict(observations: Any, mask: np.ndarray) -> Any:
    """A copy of an observation table keeping only the masked rows.

    `ends_at` is REBASED into the restricted table's index space. It indexes rows
    of the table it belongs to, and `purged_walk_forward` compares it against
    positions in that table; carrying the old absolute values into a table five
    hundred times smaller would purge either everything or nothing. This exact
    confusion between the two index spaces already voided two t-statistics in
    this package.
    """
    from .dataset import Observations

    rows = np.where(mask)[0]
    order = {int(row): i for i, row in enumerate(rows)}
    ends = np.array(
        [
            # The label ends on some bar of the FULL table. Its position here is
            # the first kept row at or after it, and the last kept row when the
            # window resolves past the end of the restriction.
            order.get(int(end), _next_kept(order, rows, int(end)))
            for end in observations.ends_at[rows]
        ],
        dtype=np.int64,
    )
    return Observations(
        X=observations.X[rows],
        y=observations.y[rows],
        ret=observations.ret[rows],
        ends_at=ends,
        names=list(observations.names),
        symbols=observations.symbols[rows],
        timestamps=observations.timestamps[rows],
        meta=dict(observations.meta),
    )


def _next_kept(order: dict[int, int], rows: np.ndarray, end: int) -> int:
    """Position of the first kept row at or after `end`, else the last one."""
    position = int(np.searchsorted(rows, end, side="left"))
    return min(position, len(rows) - 1)


def main(argv: list[str] | None = None) -> int:
    from quantlab_intraday.dataset import DEFAULT_SYMBOLS, LOCK, IntradayDataset

    from . import dataset as ml_dataset

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--target", type=float, default=2.0)
    parser.add_argument("--stop", type=float, default=1.0)
    parser.add_argument("--horizon", type=int, default=864)
    parser.add_argument("--folds", type=int, default=6)
    parser.add_argument("--embargo", type=int, default=864)
    parser.add_argument("--minimum-train", type=int, default=2_000)
    parser.add_argument("--hour", type=int, default=ITSM_HOUR)
    parser.add_argument(
        "--out", default="research/agent_runs/meta/itsm-h6.json", help="table path"
    )
    args = parser.parse_args(argv)

    symbols = [s for s in args.symbols.split(",") if s]
    data = IntradayDataset(args.data_root, LOCK, symbols, interval=args.interval)
    barriers = Barriers(args.target, args.stop, args.horizon)

    print("building the research candidate table ...", flush=True)
    research_bars = data.research()
    research_all = ml_dataset.build(research_bars, barriers, store=data.indicators)
    research = restrict(
        research_all, candidates(research_all.timestamps, hour=args.hour)
    )
    research_sigma = barrier_sigma(research, research_bars, args.horizon)
    print(f"  {len(research.y):,} candidates of {len(research_all.y):,} rows")

    # The sealed half. Features are causal, so building them over the combined
    # tape is not a leak; the model that scores them was fitted before the lock.
    print("building the 2026 candidate table ...", flush=True)
    forward_bars = data.combined()
    forward_all = ml_dataset.build(forward_bars, barriers, store=data.indicators)
    after_lock = np.array(
        [stamp > data.lock for stamp in forward_all.timestamps], dtype=bool
    )
    forward = restrict(
        forward_all, candidates(forward_all.timestamps, hour=args.hour) & after_lock
    )
    forward_sigma = barrier_sigma(forward, forward_bars, args.horizon)
    print(f"  {len(forward.y):,} candidates after {data.lock:%Y-%m-%d}")

    print("fitting the walk-forward and the final model ...", flush=True)
    verdicts, document = build_table(
        research,
        research_sigma,
        forward,
        forward_sigma,
        folds=args.folds,
        embargo=args.embargo,
        minimum_train=args.minimum_train,
    )

    payload = {
        "built_at": datetime.now().astimezone().isoformat(),
        "lock": data.lock.isoformat(),
        **document,
        "table": [v.document() for v in verdicts],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, default=str))
    print(
        json.dumps(
            {k: v for k, v in document.items() if k != "feature_names"}, indent=1
        )
    )
    positive = sum(1 for v in verdicts if v.value > 0)
    print(f"\n{positive:,} of {len(verdicts):,} candidates pass at margin 0.0")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
