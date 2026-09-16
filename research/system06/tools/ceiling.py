"""The CEILING: what a perfect forecaster would earn under OUR OWN constraints.

    PYTHONPATH=trading-system python research/system06/tools/ceiling.py

Operator, 2026-09-02: *"calcular el máximo posible de ganancia, y luego intentar
acercarte ahí"*. Until now this project measured what the book DID and compared it to
zero. That says nothing about whether +30% a year is a demanding target or an
impossible one - and a target nobody can hit is not a target, it is a way to keep
being disappointed.

So: give the strategy PERFECT FORESIGHT and nothing else. It still pays every real
cost, still holds at most `max_positions` names at once, still sizes each entry the
way the shipping book sizes it, still pays market impact on the way in and out, still
cannot buy more than `max_participation` of a bar. The only thing it gains is knowing
the future. Whatever it earns is the ceiling of THIS design - not of trading.

Three columns, because the gap between them is where the work is:

  ORACLE      perfect foresight, our constraints, our costs        <- the ceiling
  ACHIEVED    what the shipping champion actually earned
  CAPTURE     achieved / oracle, the fraction of the possible we take

Reading it: if the oracle itself cannot clear +30% in a year, no model will and the
constraint is the RISK LAYER, not the forecaster. If it clears it easily and we take
2% of it, the constraint is the forecaster and every hour belongs there.

The scheduler is greedy on net return per leg, which is not provably optimal for
overlapping slots but is a lower bound on the true optimum - so the ceiling reported
here is, if anything, conservative.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
YEARS = list(range(2018, 2027))
SEALED = 2026


def main() -> int:
    sys.path.insert(0, "trading-system")
    from system006_oracle_net_15m import attribution, launch, oracle, universe
    from system006_oracle_net_15m.dataset import Dataset

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    risk = best["risk"]
    max_positions = int(risk["max_positions"])
    # The shipping book sizes an entry as equity * deploy / max_positions, and the
    # regime module supplies deploy = regime_deploy. Same arithmetic here, so the
    # ceiling is the ceiling of THIS book rather than of an imaginary one.
    deploy = float(risk.get("regime_deploy") or risk["position_fraction"])
    per_fraction = deploy / max_positions
    max_part = float(risk.get("max_participation") or 0.0)
    min_notional = float(risk.get("min_notional") or 0.0)
    commission = launch.COMMISSION_BPS / 10_000.0
    slippage = launch.SLIPPAGE_BPS / 10_000.0
    impact = launch.IMPACT_BPS / 10_000.0
    threshold = float(best["config"]["threshold"])

    print(f"ceiling model: {max_positions} slots, {per_fraction:.0%} of equity per entry, "
          f"cap {max_part:.0%} of bar value, costs {launch.COMMISSION_BPS:.0f}+"
          f"{launch.SLIPPAGE_BPS:.0f}bps + {launch.IMPACT_BPS:.0f}*sqrt(participation)")

    symbols = universe.load()
    ds = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    bars = ds.combined()

    # -- every harvestable leg, with the liquidity of its own entry bar ---------------
    legs: list[dict] = []
    for sym, series in bars.items():
        close = np.array([b.close for b in series], float)
        vol = np.array([getattr(b, "volume", 0.0) for b in series], float)
        ts = np.array([attribution._ns(b.timestamp) for b in series], dtype=np.int64)
        pivots = oracle.zigzag_pivots(close, threshold)
        for a, b in zip(pivots, pivots[1:]):
            move = close[b.index] / max(close[a.index], 1e-12) - 1.0
            if move <= 0:
                continue
            legs.append({
                "symbol": sym, "start": int(ts[a.index]), "end": int(ts[b.index]),
                "gross": float(move),
                "entry_value": float(close[a.index] * vol[a.index]),
                "exit_value": float(close[b.index] * vol[b.index]),
            })
    print(f"{len(legs)} raw up-legs across {len(bars)} symbols")

    def net_of(leg: dict, notional: float) -> tuple[float, float]:
        """Net return and the notional actually tradeable, after caps and impact."""
        size = notional
        if max_part > 0:
            size = min(size, leg["entry_value"] * max_part, leg["exit_value"] * max_part)
        if size < min_notional or size <= 0:
            return 0.0, 0.0
        cost = 2 * commission + 2 * slippage
        if impact > 0:
            for v in (leg["entry_value"], leg["exit_value"]):
                if v > 0:
                    cost += impact * math.sqrt(min(1.0, size / v))
        return leg["gross"] - cost, size

    # -- greedy schedule, one independent $100k account per year ---------------------
    rows = {}
    for year in YEARS:
        y0 = attribution._ns(datetime(year, 1, 1))
        y1 = attribution._ns(datetime(year, 12, 31, 23, 59))
        mine = [l for l in legs if y0 <= l["start"] <= y1]
        # Greedy on gross return: the best legs first, subject to free slots.
        mine.sort(key=lambda l: -l["gross"])
        slots: list[list[tuple[int, int]]] = [[] for _ in range(max_positions)]
        taken = []
        for leg in mine:
            for slot in slots:
                if all(leg["end"] <= s or leg["start"] >= e for s, e in slot):
                    slot.append((leg["start"], leg["end"]))
                    taken.append(leg)
                    break
        taken.sort(key=lambda l: l["start"])
        equity = 100_000.0
        trades = 0
        for leg in taken:
            netpct, size = net_of(leg, equity * per_fraction)
            if size <= 0 or netpct <= 0:
                continue
            equity += size * netpct
            trades += 1
        rows[year] = {"oracle_return": equity / 100_000.0 - 1.0,
                      "oracle_trades": trades,
                      "legs_available": len(mine)}
        print(f"  {year}: oracle {rows[year]['oracle_return']:+12.2%} on {trades} trades "
              f"({len(mine)} legs available)", flush=True)

    achieved = {**{int(y): v for y, v in (best.get("annual_returns") or {}).items()},
                SEALED: (best.get("forward_2026") or {}).get("return_pct")}

    print("\n" + "=" * 92)
    print("THE CEILING - perfect foresight under OUR constraints, vs what we take")
    print("=" * 92)
    print(f"{'year':>6} {'ORACLE ceiling':>17} {'ACHIEVED':>14} {'capture':>9} {'legs':>7}")
    order = [SEALED] + [y for y in YEARS if y != SEALED]
    for y in order:
        r = rows.get(y)
        if not r:
            continue
        a = achieved.get(y)
        cap = (a / r["oracle_return"]) if (a is not None and r["oracle_return"] > 0) else None
        mark = "  <-- SEALED" if y == SEALED else ""
        print(f"{y:>6} {r['oracle_return']:>+16.2%} "
              f"{('%+.2f%%' % (100 * a)) if a is not None else '—':>14} "
              f"{(('%.2f%%' % (100 * cap)) if cap is not None else '—'):>9} "
              f"{r['legs_available']:>7}{mark}")

    out = ROOT / "rnd" / f"ceiling_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(),
        "model": {"max_positions": max_positions, "per_fraction": per_fraction,
                  "max_participation": max_part, "min_notional": min_notional,
                  "commission_bps": launch.COMMISSION_BPS,
                  "slippage_bps": launch.SLIPPAGE_BPS, "impact_bps": launch.IMPACT_BPS},
        "years": {str(y): {**rows[y], "achieved": achieved.get(y)} for y in rows},
    }, indent=1), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
