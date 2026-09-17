"""The exit question, asked of the REAL instrument, with no training at all.

`tools/exits.py` measured one entry at a time and found the way out worth five times the
mean return (+0.44% under the shipping band exit against +2.07% for a flat four-day
hold, on the same 297,730 entries). That study has one hole it cannot fill: it prices
every entry as though capital were free. A book with three slots cannot hold four days
of positions and keep taking new ones, so the portfolio may collect none of it.

The hole is closed by running the same variants through the frozen instrument - the same
`launch.per_year` every experiment uses, the same costs, the same account - which is
possible here without a single epoch of training, because **the exit levers do not touch
the net**. The signals are the champion's shipped ones; only `exit_`, `min_hold`,
`stop_loss` and `trail_stop` move. That turns a six-hour GPU row into a half-hour CPU run
and leaves the card to the reseeded confirmation (P59).

    python research/system06/tools/exit_arms.py            # all arms, 8 research years
    python research/system06/tools/exit_arms.py --years 2022 2023 2025

Ranked on the worst year's Q (return^2 / max(drawdown, 2%)) and the consistency score,
the two numbers the operator's criterion and the mandate are written in. 2026 is not
touched: this is research, and a sealed reading is spent, never repeated.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
from datetime import datetime, timezone

REPO = pathlib.Path(__file__).resolve().parents[3]
for sub in ("backtester", "trading-system", "trading-system/systems",
            "orchestrator-manager", "live-trading"):
    sys.path.insert(0, str(REPO / sub))

DD_FLOOR = 0.02
RESEARCH_YEARS = (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025)

# One entry set, one net, one cost model. Only the way out moves.
ARMS: dict[str, dict] = {
    "baseline (live engine)": {},
    "exit 0.10": {"exit_": 0.10},
    "exit 0.05": {"exit_": 0.05},
    "exit 0.05 + stop 0.08": {"exit_": 0.05, "stop_loss": 0.08},
    "exit 0.10 + trail 0.12": {"exit_": 0.10, "trail_stop": 0.12},
    "hold 96 (1 day)": {"min_hold": 96},
    "hold 384 (4 days) + stop 0.08": {"min_hold": 384, "stop_loss": 0.08},
    "deploy 0.70 [CONTROL]": {"regime_deploy": 0.7},
}


def _quality(ret: float, dd: float) -> float:
    dd = max(float(dd or 0.0), DD_FLOOR)
    return (1.0 if ret >= 0 else -1.0) * (ret * ret) / dd


def run(engine_version: str, years=RESEARCH_YEARS) -> dict:
    from quantlab_live.engine import EnginePackage, LiveEngine
    from system006_oracle_net_15m import autoloop, launch, universe
    from system006_oracle_net_15m.dataset import Dataset
    from quantlab_catalog.paths import DATA_ROOT

    package = EnginePackage.load(engine_version)
    live = LiveEngine(package)
    band, risk = package.band, package.risk

    symbols = universe.load()
    if len(symbols) < 5:
        raise SystemExit(f"degenerate universe ({symbols!r}) - run from the repo root")
    dataset = Dataset(data_root=str(DATA_ROOT), symbols=symbols, interval="15m")
    bars = dataset.research()
    stamps = sorted({b.timestamp for series in bars.values() for b in series})

    base = {"enter": float(band["enter"]), "exit_": float(band["exit_"]),
            "min_hold": int(band["min_hold"]),
            "meta_signals": str(live.meta_path), "size_signals": str(live.money_path),
            **risk}
    signals = str(live.signals_path)

    out: dict[str, dict] = {}
    for label, extra in ARMS.items():
        started = datetime.now(timezone.utc)
        per_year = launch.per_year(bars, stamps, years, signals,
                                   brain_kwargs={**base, **extra})
        rows = {int(y): per_year[y] for y in per_year
                if (per_year[y] or {}).get("return_pct") is not None}
        cons = autoloop._consistency(per_year)
        q = {y: _quality(float(r["return_pct"]), float(r.get("max_drawdown") or 0.0))
             for y, r in rows.items()}
        out[label] = {
            "score": round(float(cons["score"]), 4),
            "min_year": round(float(cons["min_year"]), 4),
            "cagr": round(float(cons["cagr"]), 4),
            "all_positive": bool(cons["all_positive"]),
            "quality_worst": round(min(q.values()), 4) if q else None,
            "quality_median": round(statistics.median(q.values()), 4) if q else None,
            "worst_drawdown": round(max(float(r.get("max_drawdown") or 0.0)
                                        for r in rows.values()), 4) if rows else None,
            "trades": int(sum(int(r.get("trades") or 0) for r in rows.values())),
            "annual": {y: round(float(r["return_pct"]), 4) for y, r in sorted(rows.items())},
            "quality_by_year": {y: round(v, 4) for y, v in sorted(q.items())},
            "minutes": round((datetime.now(timezone.utc) - started).total_seconds() / 60, 1),
        }
        s = out[label]
        print(f"{label:<32} score {s['score']:+.4f}  worstQ {s['quality_worst']:+.4f}  "
              f"worst yr {s['min_year']:+.2%}  dd {s['worst_drawdown']:.1%}  "
              f"{s['trades']:>5} trades  [{s['minutes']:.0f}m]", flush=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine", default="v2-a83-thresholds")
    parser.add_argument("--years", nargs="*", type=int, default=list(RESEARCH_YEARS))
    args = parser.parse_args()

    print(f"engine {args.engine} | years {args.years} | no training: the net is fixed\n",
          flush=True)
    result = run(args.engine, tuple(args.years))

    base = result.get("baseline (live engine)", {})
    print("\nagainst the baseline:")
    for label, s in result.items():
        if label.startswith("baseline"):
            continue
        print(f"  {label:<32} score {s['score'] - base.get('score', 0):+.4f}   "
              f"worstQ {s['quality_worst'] - (base.get('quality_worst') or 0):+.4f}")

    payload = {"at": datetime.now(timezone.utc).isoformat(), "engine": args.engine,
               "years": args.years, "arms": ARMS, "result": result,
               "method": ("the frozen instrument, one net, exit levers only; ranked on the "
                          "worst year's Q and the consistency score; 2026 untouched")}
    out = (REPO / "research/system06/rnd"
           / f"exit_arms_{args.engine}_{datetime.now(timezone.utc):%Y-%m-%d}.json")
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\nwritten: {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
