"""Same entries, different ways out. Which exit rule is throwing the edge away?

This is the second half of the operator's 2026-09-17 instruction - *"the trades we got
wrong... on what tolerances we failed"* - and it is asked the only way that can answer
it: hold the ENTRY set fixed and vary nothing but the way out.

Why this question and not another
---------------------------------
`tools/refusals.py` priced every bar the engine admitted (no gate shut) under a plain
band exit: **+0.64% a trade across the research years, +0.69% in the sealed year.** The
trade ledger (`rnd/attribution_2026-09-02.json`) says what the book actually earned on
the trades it took: +0.195% a trade in 2018 (88.1 points over 451 trades), +0.045% in
2019 (42.76 over 942). The entries are the same population. The gap is the exit.

So the entry machinery may be fine and the exit machinery may be eating it - which is a
structural claim about where the money goes, not a guess about which number to nudge.
This measures it: one entry set, six ways out, the same cost charged to all of them.

    band          leave on the first bar below `exit_`, after `min_hold`
    band+stop     the same, but a hard stop at the engine's `stop_loss`
    band+trail    the same, but a trailing stop at `trail_stop` from the high
    shipping      band + stop + trail, which is what the engine actually runs
    horizon N     leave after N bars whatever the conviction says
    oracle_cap    the best exit in the window, for scale only - never adoptable

`oracle_cap` is hindsight and is printed to show what fraction of the available move each
honest rule captures. It is not a candidate and never will be.
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
HORIZON = 2_000          # bars to look forward: three weeks at 15 minutes
REPORT_HORIZONS = (16, 96, 384)


def _walk(high, low, close, start, limit, exit_after, stop, trail):
    """Index where this rule leaves, given the first legal exit bar `exit_after`.

    One pass per entry rather than a vectorised trick, because a trailing stop is
    path-dependent by definition: its level depends on every bar between here and there.
    """
    peak = close[start]
    end = min(start + limit, len(close) - 1)
    for j in range(start, end + 1):
        peak = max(peak, high[j])
        if stop and low[j] <= close[start] * (1.0 - stop):
            return j, "stop"
        if trail and low[j] <= peak * (1.0 - trail):
            return j, "trail"
        if j >= exit_after:
            return j, "band"
    return end, "horizon"


def study(engine_version: str, years=RESEARCH_YEARS, limit_entries: int | None = None) -> dict:
    from quantlab_live.engine import EnginePackage
    from system006_oracle_net_15m import moneymodel, universe
    from system006_oracle_net_15m.dataset import Dataset
    from system006_oracle_net_15m.modules.crowd import Crowd
    from quantlab_catalog.paths import DATA_ROOT

    package = EnginePackage.load(engine_version)
    band, risk = package.band, package.risk
    enter, exit_, min_hold = float(band["enter"]), float(band["exit_"]), int(band["min_hold"])
    stop = float(risk.get("stop_loss") or 0.0)
    trail = float(risk.get("trail_stop") or 0.0)
    breadth_gate = float(risk.get("breadth_gate") or 0.0)
    fng_min = float(risk.get("fng_min") or 0.0)
    crowd = Crowd(fng_min=fng_min or 1.0)

    cache = REPO / "live-trading" / "state" / "engine_cache" / engine_version
    signals = str(cache / "signals.npz")
    symbols = universe.load()
    bars = Dataset(data_root=str(DATA_ROOT), symbols=symbols, interval="15m").combined()
    per_sym = moneymodel._load_features(signals, str(DATA_ROOT), research=bars)

    rules = {"band": (0.0, 0.0), "band+stop": (stop, 0.0), "band+trail": (0.0, trail),
             "shipping": (stop, trail)}
    nets: dict[str, list[float]] = {k: [] for k in rules}
    nets.update({f"horizon {h}": [] for h in REPORT_HORIZONS})
    nets["oracle_cap"] = []
    reasons: dict[str, int] = {}
    entries = 0

    for sym, d in per_sym.items():
        prob, trend, ns = d["prob"], d["trend"], d["ns"]
        breadth, close = d["breadth"], d["close"]
        series = bars.get(sym) or []
        if not series:
            continue
        # The channel arrays start AFTER the net's warm-up window, so they are shorter
        # than the bar series and indexed differently. Align on the timestamp rather than
        # on position: the first version compared lengths, found them unequal for every
        # symbol, and reported zero admitted entries with a straight face.
        bar_ns = np.array([np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64")
                           for b in series], dtype=np.int64)
        pos = np.searchsorted(bar_ns, ns)
        pos = np.clip(pos, 0, len(series) - 1)
        aligned = bar_ns[pos] == ns
        high = np.array([b.high for b in series], dtype=float)
        low = np.array([b.low for b in series], dtype=float)
        close_bars = np.array([b.close for b in series], dtype=float)
        year = ns.astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970
        n = len(close)

        admitted = []
        for i in np.flatnonzero(prob >= enter):
            if i + min_hold + 2 >= n or year[i] not in years or not aligned[i]:
                continue
            if trend[i] <= 0:
                continue
            if breadth_gate and breadth[i] < breadth_gate:
                continue
            if fng_min:
                fg = crowd.value_at(int(ns[i]))
                if fg is not None and fg < fng_min:
                    continue
            admitted.append(int(i))
        if limit_entries:
            admitted = admitted[:limit_entries]

        # The first bar at or after which the band rule is allowed to leave.
        nb = len(series)
        for i in admitted:
            # `i` indexes the channels; `b` the bars. The walk happens in bar space.
            b = int(pos[i]) + 1
            if b + min_hold + 2 >= nb:
                continue
            legal_ch = i + 1 + min_hold
            below = np.flatnonzero(prob[legal_ch:min(legal_ch + HORIZON, n)] < exit_)
            exit_ch = legal_ch + int(below[0]) if len(below) else n - 1
            start = b
            exit_after = int(pos[min(exit_ch, n - 1)])
            entry_px = close_bars[start]
            if not np.isfinite(entry_px) or entry_px <= 0:
                continue
            entries += 1
            for name, (s_, t_) in rules.items():
                j, why = _walk(high, low, close_bars, start, HORIZON, exit_after, s_, t_)
                px = close_bars[start] * (1.0 - s_) if why == "stop" else close_bars[j]
                nets[name].append(float(px / entry_px - 1.0 - ROUND_TRIP))
                if name == "shipping":
                    reasons[why] = reasons.get(why, 0) + 1
            for h in REPORT_HORIZONS:
                j = min(start + h, nb - 1)
                nets[f"horizon {h}"].append(float(close_bars[j] / entry_px - 1.0 - ROUND_TRIP))
            window = close_bars[start:min(start + HORIZON, nb)]
            nets["oracle_cap"].append(float(window.max() / entry_px - 1.0 - ROUND_TRIP))

    out = {"engine": engine_version, "entries": entries,
           "band": {k: band[k] for k in ("enter", "exit_", "min_hold")},
           "stop_loss": stop, "trail_stop": trail,
           "shipping_exit_reasons": reasons, "rules": {}}
    for name, values in nets.items():
        a = np.array(values, dtype=float)
        if not len(a):
            continue
        out["rules"][name] = {"n": len(a), "mean_net": round(float(a.mean()), 5),
                              "median_net": round(float(np.median(a)), 5),
                              "win_rate": round(float((a > 0).mean()), 4),
                              "sum_net": round(float(a.sum()), 2)}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine", default="v2-a83-thresholds")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the entries per symbol (a smoke test, not a result)")
    args = parser.parse_args()

    result = study(args.engine, limit_entries=args.limit)
    print(f"engine {args.engine}  |  {result['entries']:,} admitted entries, research years\n")
    print(f"{'exit rule':<16}{'mean net':>11}{'median':>10}{'win rate':>10}{'sum':>12}")
    print("-" * 59)
    for name, s in result["rules"].items():
        print(f"{name:<16}{s['mean_net']:>10.2%}{s['median_net']:>10.2%}"
              f"{s['win_rate']:>10.1%}{s['sum_net']:>12.1f}")
    print(f"\nshipping rule left because: {result['shipping_exit_reasons']}")

    out = (REPO / "research/system06/rnd"
           / f"exits_{args.engine}_{datetime.now(timezone.utc):%Y-%m-%d}.json")
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"written: {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
