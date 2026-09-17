"""Which GATE refused each trade we never took, and what that refusal was worth.

Operator, 2026-09-17: *"the tests we run have to make sense. They cannot be random or
looking for random values... I would base it on two things: the trades we got wrong and
the trades we did not take, and on what tolerances we failed, or on what tolerances we
did not enter. One a day if it is thought through, rather than fifty empty ones."*

`attribution.py` already answers the first half - it partitions a year into won, lost,
unforced and missed. What it cannot say is WHY a missed leg was missed, and that is the
half a change can actually be aimed at. This file answers it.

The method, and why it is not a sweep
-------------------------------------
Every bar where the net wanted in (`prob >= enter`) is a decision the system made. At
that bar the entry survives or dies at one of four gates, each a single number in the
engine's configuration:

    trend    the causal slow-trend bit must be up
    breadth  the fraction of the universe in an uptrend must clear `breadth_gate`
    fear     the PUBLISHED Fear & Greed index must clear `fng_min`
    meta     the meta-label's expected net must clear `meta_margin`

For every one of those bars this measures the COUNTERFACTUAL: what the trade would have
returned had it been taken, under the engine's own exit rule (hold at least `min_hold`
bars, then leave on the first bar whose conviction falls below `exit_`), charged the
round trip. Then it attributes that outcome to whichever gates were shut.

The result is a ledger with one line per gate: how many entries it refused, what those
entries would have made or lost, and therefore whether the gate is paying for itself.
A gate that refused four hundred entries averaging -2% is earning its place; a gate that
refused ninety averaging +6% is the most expensive line in the system, and the next
experiment writes itself.

Two honesties
-------------
* The counterfactual uses the engine's exit rule but NOT its book: no slot limit, no
  cash, no position already open. So a refused entry is priced as though capital had
  been free. That overstates what the gates cost - deliberately, because it means a gate
  this table clears is cleared with room to spare.
* Fitting is restricted to the research years. 2026 rows are printed as a READOUT and
  never used to choose anything, for the same reason `attribution.explain` refuses them.

    python research/system06/tools/refusals.py --engine v2-a83-thresholds
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[3]
for sub in ("backtester", "trading-system", "trading-system/systems",
            "orchestrator-manager", "live-trading"):
    sys.path.insert(0, str(REPO / sub))

ROUND_TRIP = 0.003
RESEARCH_YEARS = tuple(range(2018, 2026))
SEALED = 2026
GATES = ("trend", "breadth", "fear", "meta")


def _first_below(prob: np.ndarray, level: float) -> np.ndarray:
    """`out[i]` = the first index >= i whose conviction is below `level` (len if none).

    One backward pass instead of a scan per candidate: with fourteen symbols and three
    million bars the naive version is the difference between a minute and an afternoon.
    """
    n = len(prob)
    out = np.full(n + 1, n, dtype=np.int64)
    for i in range(n - 1, -1, -1):
        out[i] = i if prob[i] < level else out[i + 1]
    return out[:n]


def _year_of(ns: np.ndarray) -> np.ndarray:
    return ns.astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970


def ledger(engine_version: str | None = None, signals: str | None = None,
           meta_path: str | None = None, band: dict | None = None,
           risk: dict | None = None) -> dict:
    """The refusal ledger for one engine configuration."""
    from quantlab_live.engine import EnginePackage
    from system006_oracle_net_15m import moneymodel, universe
    from system006_oracle_net_15m.dataset import Dataset
    from quantlab_catalog.paths import DATA_ROOT

    if engine_version:
        package = EnginePackage.load(engine_version)
        band = band or package.band
        risk = risk or package.risk
        cache = REPO / "live-trading" / "state" / "engine_cache" / engine_version
        signals = signals or str(cache / "signals.npz")
        meta_path = meta_path or str(cache / "meta.npz")
    if not pathlib.Path(signals).is_file():
        raise SystemExit(f"no signals at {signals} - run the trader once to build them")

    enter = float(band["enter"])
    exit_ = float(band["exit_"])
    min_hold = int(band["min_hold"])
    breadth_gate = float(risk.get("breadth_gate") or 0.0)
    fng_min = float(risk.get("fng_min") or 0.0)
    meta_margin = risk.get("meta_margin")
    meta_margin = None if meta_margin is None else float(meta_margin)

    # The fear gate reads the PUBLISHED index (0-100, daily, external file), not the
    # per-bar causal `feargreed` channel, which lives in [0,1]. Comparing the channel
    # against fng_min made the first version of this table refuse 89% of every bar and
    # report zero admitted entries - a units error that looked like a finding.
    from system006_oracle_net_15m.modules.crowd import Crowd  # noqa: PLC0415

    crowd = Crowd(fng_min=fng_min or 1.0)

    symbols = universe.load()
    bars = Dataset(data_root=str(DATA_ROOT), symbols=symbols, interval="15m").combined()
    per_sym = moneymodel._load_features(signals, str(DATA_ROOT), research=bars)

    verdicts: dict[str, dict[int, float]] = {}
    if meta_margin is not None and meta_path and pathlib.Path(meta_path).is_file():
        # `write_meta` stores one pair per symbol: SYM__meta_ns and SYM__meta.
        z = np.load(meta_path)
        for key in z.files:
            if key.endswith("__meta_ns"):
                sym = key[: -len("__meta_ns")]
                if f"{sym}__meta" in z.files:
                    verdicts[sym] = dict(zip(z[key].astype(np.int64).tolist(),
                                             z[f"{sym}__meta"].astype(float).tolist()))

    rows: list[dict] = []
    for sym, d in per_sym.items():
        prob, trend, close = d["prob"], d["trend"], d["close"]
        ns, breadth, fear = d["ns"], d["breadth"], d["feargreed"]
        n = len(prob)
        if n < min_hold + 2:
            continue
        below = _first_below(prob, exit_)
        want = np.flatnonzero(prob >= enter)
        want = want[want + min_hold + 1 < n]
        if not len(want):
            continue
        meta_for = verdicts.get(sym, {})
        years = _year_of(ns)
        for i in want:
            entry_i = i + 1                      # the engine fills on the NEXT bar
            exit_i = int(min(below[min(entry_i + min_hold, n - 1)], n - 1))
            entry_px, exit_px = close[entry_i], close[exit_i]
            if not np.isfinite(entry_px) or not np.isfinite(exit_px) or entry_px <= 0:
                continue
            net = float(exit_px / entry_px - 1.0 - ROUND_TRIP)
            shut = []
            if trend[i] <= 0:
                shut.append("trend")
            if breadth_gate and breadth[i] < breadth_gate:
                shut.append("breadth")
            if fng_min:
                published = crowd.value_at(int(ns[i]))
                if published is not None and published < fng_min:
                    shut.append("fear")
            if meta_margin is not None:
                verdict = meta_for.get(int(ns[i]))
                if verdict is not None and verdict < meta_margin:
                    shut.append("meta")
            rows.append({"symbol": sym, "year": int(years[i]), "ns": int(ns[i]),
                         "net": net, "shut": shut, "held_bars": exit_i - entry_i,
                         "prob": float(prob[i]), "breadth": float(breadth[i]),
                         "fear_index": crowd.value_at(int(ns[i])),
                         "fear_channel": float(fear[i])})

    return {"engine": engine_version, "band": band, "risk":
            {k: risk.get(k) for k in ("breadth_gate", "fng_min", "meta_margin",
                                      "max_positions", "position_fraction")},
            "rows": rows}


def summarise(rows: list[dict], years=RESEARCH_YEARS) -> dict:
    """One line per gate: what it refused, and what the refusal was worth."""
    keep = [r for r in rows if r["year"] in years]
    out: dict[str, dict] = {}

    admitted = [r for r in keep if not r["shut"]]
    out["ADMITTED (no gate shut)"] = _stats(admitted)

    for gate in GATES:
        refused = [r for r in keep if gate in r["shut"]]
        only = [r for r in refused if r["shut"] == [gate]]
        out[gate] = {**_stats(refused), "alone": _stats(only)}
    return out


def _stats(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "mean_net": None, "sum_net": None, "win_rate": None,
                "median_hold_bars": None}
    nets = np.array([r["net"] for r in rows], dtype=float)
    return {"n": len(rows),
            "mean_net": round(float(nets.mean()), 5),
            "sum_net": round(float(nets.sum()), 3),
            "win_rate": round(float((nets > 0).mean()), 4),
            "median_hold_bars": int(np.median([r["held_bars"] for r in rows]))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine", default="v2-a83-thresholds")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    book = ledger(engine_version=args.engine)
    rows = book["rows"]
    research = summarise(rows, RESEARCH_YEARS)
    sealed = summarise(rows, (SEALED,))

    print(f"engine {args.engine}  |  {len(rows):,} bars where the net wanted in\n")
    head = f"{'gate':<26}{'refused':>9}{'mean net':>11}{'sum net':>11}{'win rate':>10}"
    print(head)
    print("-" * len(head))
    for name, s in research.items():
        if s["n"] == 0:
            print(f"{name:<26}{0:>9}")
            continue
        print(f"{name:<26}{s['n']:>9,}{s['mean_net']:>10.2%}{s['sum_net']:>11.1f}"
              f"{s['win_rate']:>10.1%}")
        alone = s.get("alone")
        if alone and alone["n"]:
            print(f"{'  ...and nothing else':<26}{alone['n']:>9,}{alone['mean_net']:>10.2%}"
                  f"{alone['sum_net']:>11.1f}{alone['win_rate']:>10.1%}")

    print("\nREADOUT ONLY - the sealed year, never used to choose anything:")
    for name, s in sealed.items():
        if s["n"]:
            print(f"  {name:<24}{s['n']:>9,}{s['mean_net']:>10.2%}{s['win_rate']:>10.1%}")

    payload = {"at": datetime.now(timezone.utc).isoformat(), "engine": args.engine,
               "band": book["band"], "risk": book["risk"],
               "research": research, "sealed_readout": sealed,
               "method": ("every bar where prob >= enter, priced under the engine's own "
                          "exit rule (min_hold then first bar below exit_), charged 30 bps, "
                          "with no book constraint - so a gate that clears here clears with "
                          "room to spare")}
    out = pathlib.Path(args.out or REPO / "research/system06/rnd"
                       / f"refusals_{args.engine}_{datetime.now(timezone.utc):%Y-%m-%d}.json")
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\nwritten: {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
