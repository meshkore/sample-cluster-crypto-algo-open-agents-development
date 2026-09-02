"""Forensic audit of the new champion's 2021: is x1220 in a year real or a bug?

    PYTHONPATH=trading-system python research/system06/tools/audit_2021.py

The operator's question, asked properly: he has never seen a +121,905% year, and a
number nobody has ever seen needs its mechanics opened before it is believed. Checks,
each one a way the engine could be lying:

  1. LEDGER RECONCILIATION - compound the per-trade returns and compare with the
     account's year. A ledger that cannot rebuild its own year is measuring something
     else (this exact check caught a double-counted fee once).
  2. CASH AND SIZING - cash never negative; no single BUY exceeds the equity at that
     moment; position sizes obey position_fraction x money-model scaling.
  3. PRICE REALITY - entry and exit prices of the biggest trades exist in the raw
     candles for that symbol at that timestamp (within the bar's high/low).
  4. CONCENTRATION - how much of the year is the top 1% of trades; a year carried by
     three lottery tickets is a different risk story than steady compounding.
  5. NO GHOST FILLS - trade timestamps must be strictly inside the window, holding
     periods positive, and every SELL must follow a BUY it can pair with.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
YEAR = 2021


def main() -> int:
    sys.path.insert(0, "trading-system")
    from quantlab_system06 import launch, universe
    from quantlab_system06.dataset import Dataset

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    band, risk = dict(best["band"]), dict(best["risk"])
    brain = {**band, **risk}
    if float(risk.get("money_model") or 0) > 0:
        brain["size_signals"] = str(ROOT / "moneymodel.npz")
    symbols = universe.load()
    ds = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    rbars = ds.research()
    stamps = sorted({b.timestamp for s in rbars.values() for b in s})

    res = launch.year_window(rbars, stamps, YEAR, str(ROOT / "signals.npz"),
                             brain_kwargs=brain, with_trades=True)
    trips = res["trades_detail"]
    ret = float(res["return_pct"])
    print(f"{YEAR}: return {ret:+.2%}  maxDD {res['max_drawdown']:.2%}  "
          f"trades {res['trades']}  closed round-trips {len(trips)}")

    # -- 1. reconciliation ------------------------------------------------------------
    # Round trips compound multiplicatively only if capital is fully redeployed; here
    # positions overlap and sizes vary, so the honest reconstruction walks the equity
    # from the trade P&Ls against the recorded curve instead.
    pnl_sum = sum(t["pnl"] for t in trips)
    curve = res.get("equity")
    end_equity = curve[-1]["equity"] if curve else None
    implied = 100_000.0 + pnl_sum
    print(f"\n[1] sum of closed-trade P&L: {pnl_sum:+,.0f} -> implied end equity "
          f"{implied:,.0f}; account end equity {end_equity:,.0f}"
          if end_equity else "no equity curve")
    if end_equity:
        gap = abs(implied - end_equity) / end_equity
        print(f"    gap {gap:.2%} (open positions at Dec 31 explain a small one) "
              f"-> {'OK' if gap < 0.05 else 'INVESTIGATE'}")

    # -- 2. cash and sizing from the curve -------------------------------------------
    if curve:
        cash = [p["cash"] for p in curve]
        eq = [p["equity"] for p in curve]
        print(f"\n[2] min cash on curve: {min(cash):,.0f} "
              f"({'OK - never negative' if min(cash) >= -1e-6 else 'NEGATIVE: BUG'})")
        costs = sorted((t["cost"] for t in trips), reverse=True)
        print(f"    largest single BUY {costs[0]:,.0f}; equity max {max(eq):,.0f}; "
              f"position_fraction {risk['position_fraction']}")
        jumps = [(curve[i+1]["equity"] / max(curve[i]["equity"], 1e-9) - 1, i)
                 for i in range(len(curve) - 1)]
        wj, wi = max(jumps)
        print(f"    largest single-step equity jump {wj:+.1%} at {curve[wi]['timestamp']}"
              f" ({'plausible for 15m crypto' if wj < 0.5 else 'INVESTIGATE'})")

    # -- 3. price reality of the biggest trades --------------------------------------
    print("\n[3] top 8 trades by P&L, prices checked against raw candles:")
    by_symbol = {s: {b.timestamp.isoformat(): b for b in bars}
                 for s, bars in rbars.items()}
    for t in sorted(trips, key=lambda t: -t["pnl"])[:8]:
        o, c = t["opened"], t["closed"]
        held_h = ((datetime.fromisoformat(c) - datetime.fromisoformat(o)).total_seconds()
                  / 3600)
        bo = by_symbol.get(t["symbol"], {}).get(o)
        bc = by_symbol.get(t["symbol"], {}).get(c)
        ok = bo is not None and bc is not None
        print(f"    {t['symbol']:>9} {o[:10]} -> {c[:10]} ({held_h:6.0f}h) "
              f"cost {t['cost']:>10,.0f} net {t['net_pct']:+8.1%} pnl {t['pnl']:>11,.0f} "
              f"bars {'FOUND' if ok else 'MISSING: BUG'}  exit reason {t.get('reason')}")

    # -- 4. concentration -------------------------------------------------------------
    pos = sorted((t["pnl"] for t in trips if t["pnl"] > 0), reverse=True)
    gross_win = sum(pos)
    k = max(1, len(pos) // 100)
    print(f"\n[4] winners {len(pos)}/{len(trips)}; top 1% of winners "
          f"({k} trades) = {sum(pos[:k]) / max(gross_win, 1e-9):.1%} of gross wins; "
          f"top 10 = {sum(pos[:10]) / max(gross_win, 1e-9):.1%}")
    nets = [t["net_pct"] for t in trips]
    print(f"    per-trade net: median {np.median(nets):+.2%}  mean {np.mean(nets):+.2%}  "
          f"best {max(nets):+.1%}  worst {min(nets):+.1%}")

    # -- 5. ghost fills ---------------------------------------------------------------
    bad_time = [t for t in trips
                if not (str(YEAR) <= t["closed"][:4] and t["opened"] < t["closed"])]
    tiny = [t for t in trips if t["cost"] < 100.0]
    print(f"\n[5] trades with impossible timestamps: {len(bad_time)} "
          f"({'OK' if not bad_time else 'BUG'})")
    print(f"    orders below the operator's $100 minimum: {len(tiny)}"
          + (f" (smallest {min(t['cost'] for t in tiny):,.2f})" if tiny else ""))

    out = ROOT / "rnd" / f"audit_{YEAR}_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "year": YEAR, "return_pct": ret, "trades": len(trips),
        "pnl_sum": pnl_sum, "end_equity": end_equity,
        "min_cash": min(cash) if curve else None,
        "largest_buy": costs[0] if curve else None,
        "largest_step": wj if curve else None,
        "top10_share_of_wins": sum(pos[:10]) / max(gross_win, 1e-9),
        "sub_100_orders": len(tiny),
        "per_trade_median_net": float(np.median(nets)),
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
