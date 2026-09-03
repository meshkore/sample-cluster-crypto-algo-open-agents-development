"""THE BASE WE TRADE ON: what each year of this market actually offered.

    PYTHONPATH=trading-system python research/system06/tools/market_base.py

Operator, 2026-09-03: the "máximo potencial" page should stop mixing in how much WE
captured and instead describe the ground itself - "volúmenes, número de assets
disponibles cada año, número de trades, la media del profit de cada trade". Capture
belongs next to a strategy's own figures, not next to the market's.

So this is a pure description of the playing field, computed once and served as static
facts. Nothing here is a result and nothing here is optimised against; it is the answer
to "what was there to be taken", which is the only honest denominator for anything the
laboratory later claims.

Per calendar year, over the 14-symbol universe at 15m:

  assets            how many of the 14 had ANY data that year (the universe grows -
                    SUI and WLD did not exist in 2018, and a year with 9 listed coins
                    is a smaller opportunity than a year with 14)
  bars              15m candles across all listed symbols
  traded_value      sum of volume x close over every bar: the money that actually
                    changed hands in front of us. This is the hard limit behind the
                    10%-of-bar participation cap - it is why a $50k order is invisible
                    in BTC and moves the price in a thin altcoin.
  median_bar_value  the typical single candle's traded value, per symbol - the number
                    the impact model is calibrated against
  legs_available    up-swings the perfect-hindsight oracle could see (from ceiling.py):
                    every opportunity that existed, before any constraint
  oracle_trades     how many of those it could actually TAKE under our own limits -
                    2 slots at a time, minimum $100, max 10% of a bar
  oracle_return     what taking them earned, net of every real cost
  avg_per_trade     the geometric average profit of ONE of those trades: the size of a
                    single perfect decision. It is the most sobering number here -
                    perfect foresight does not mean huge individual wins, it means
                    never taking a bad one.

Read together: `legs_available` vs `oracle_trades` is what our own risk limits cost even
a perfect forecaster, and `avg_per_trade` is what one flawless decision is worth.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
OUT = ROOT / "rnd" / "market_base.json"


def main() -> int:
    sys.path.insert(0, "trading-system")
    from quantlab_system06 import universe
    from quantlab_system06.dataset import Dataset

    syms = universe.load()
    print(f"universe: {len(syms)} symbols", flush=True)
    ds = Dataset(data_root=DATA, symbols=syms, interval="15m")
    bars = ds.combined()          # research history + the sealed 2026 window

    # The ceiling run already knows what was THERE to be taken; reuse it rather than
    # recomputing the oracle, and fail loudly if it is missing instead of quietly
    # publishing a page with holes in it.
    ceils = sorted((ROOT / "rnd").glob("ceiling_*.json"))
    if not ceils:
        print("no ceiling_*.json — run tools/ceiling.py first", file=sys.stderr)
        return 1
    ceiling = json.loads(ceils[-1].read_text(encoding="utf-8"))
    cyears = ceiling.get("years") or {}

    years: dict[str, dict] = {}
    for sym, series in bars.items():
        for b in series:
            y = str(b.timestamp.year)
            slot = years.setdefault(y, {"assets": set(), "bars": 0,
                                        "traded_value": 0.0, "_per_bar": []})
            slot["assets"].add(sym)
            slot["bars"] += 1
            v = float(b.volume) * float(b.close)
            slot["traded_value"] += v
            slot["_per_bar"].append(v)

    out: dict[str, dict] = {}
    for y in sorted(years):
        if y < "2018":
            continue          # partial listing history before the research window
        s = years[y]
        per = sorted(s["_per_bar"])
        median = per[len(per) // 2] if per else 0.0
        c = cyears.get(y) or {}
        legs = c.get("legs_available")
        trades = c.get("oracle_trades")
        oret = c.get("oracle_return")
        # Geometric, not arithmetic: the trades compound inside the year, so the average
        # single trade is the n-th root of the year's multiple, never total/n.
        avg = ((1 + oret) ** (1 / trades) - 1) if (oret is not None and trades) else None
        out[y] = {
            "assets": len(s["assets"]),
            "bars": s["bars"],
            "traded_value": s["traded_value"],
            "median_bar_value": median,
            "legs_available": legs,
            "oracle_trades": trades,
            "oracle_return": oret,
            "avg_per_trade": avg,
        }
        print(f"  {y}: {len(s['assets']):2d} assets · {s['bars']:>8,} bars · "
              f"${s['traded_value']/1e9:8.1f}B traded · legs {legs} · "
              f"oracle trades {trades} · avg/trade "
              f"{f'{avg:+.2%}' if avg is not None else '—'}", flush=True)

    OUT.write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(),
        "universe": sorted(syms),
        "timeframe": "15m",
        "source_ceiling": ceils[-1].name,
        "cost_model": ceiling.get("model"),
        "years": out,
    }, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT} ({len(out)} years)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
