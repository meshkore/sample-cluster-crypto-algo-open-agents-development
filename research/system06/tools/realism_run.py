"""The champion measured under EXECUTION REALISM, side by side with the raw table.

    PYTHONPATH=trading-system python research/system06/tools/realism_run.py

Operator, 2026-09-02, after the audit found $45M orders in single 15-minute candles:
every year starts with $100,000 on the table (that is already the measurement design -
launch.per_year opens each calendar year as an independent account at INITIAL_CAPITAL),
no order below $100, and a maximum decided by money management. The maximum used here:
no BUY may exceed 10% of the value actually traded in that bar, because a backtest
paying 15 bps on an order the size of half the bar's volume is quoting a market that
does not exist.

Both levers are off-by-default engine features (test_execution_realism.py); this run
measures what they change. Expected shape, stated before running: small years barely
move (a $15k order in BTC is invisible), and the monster years deflate exactly where
the account outgrew the market - which is the honest number the operator asked for.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
SEALED = 2026
MIN_NOTIONAL = 100.0
MAX_PARTICIPATION = 0.10


def main() -> int:
    sys.path.insert(0, "trading-system")
    from system006_oracle_net_15m import launch, universe
    from system006_oracle_net_15m.dataset import Dataset

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    base = {**best["band"], **best["risk"]}
    if float(best["risk"].get("money_model") or 0) > 0:
        base["size_signals"] = str(ROOT / "moneymodel.npz")
    real = {**base, "min_notional": MIN_NOTIONAL, "max_participation": MAX_PARTICIPATION}
    # NOTE (2026-09-02, second run): once the caps were ADOPTED into best.json's risk
    # block, `base` started carrying them too and both columns printed the same number.
    # The arms are named for what they actually differ in, so a future reader is not
    # invited to read an identity as a finding. The live question moved into the shared
    # engine anyway: market impact is a CostModel property, not a brain lever, so it
    # applies to both arms and is measured by comparing against the recorded history.
    base = {k: v for k, v in base.items()
            if k not in ("min_notional", "max_participation")}

    symbols = universe.load()
    ds = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    bars = ds.combined()
    stamps = sorted({b.timestamp for s in bars.values() for b in s})
    sig = str(ROOT / "signals.npz")
    years = list(range(2018, 2027))

    rows = {}
    for label, kw in (("raw", base), ("realistic", real)):
        print(f"\n=== {label} ===", flush=True)
        for y in years:
            r = launch.year_window(bars, stamps, y, sig, brain_kwargs=kw)
            if r:
                rows.setdefault(y, {})[label] = {
                    "return_pct": r["return_pct"], "max_drawdown": r["max_drawdown"],
                    "trades": r["trades"]}
                print(f"  {y}: {r['return_pct']:+10.2%}  dd {r['max_drawdown']:5.1%}  "
                      f"trades {r['trades']}", flush=True)

    print("\n" + "=" * 88)
    print("EACH YEAR AN INDEPENDENT $100,000 ACCOUNT - raw engine vs execution realism")
    print(f"(realism: min order ${MIN_NOTIONAL:.0f}, max {MAX_PARTICIPATION:.0%} of each "
          "bar's traded value)")
    print("=" * 88)
    print(f"{'year':>6} {'raw':>12} {'realistic':>12} {'raw dd':>8} {'real dd':>8}"
          f" {'trades':>7}")
    order = [SEALED] + [y for y in years if y != SEALED and y in rows]
    for y in order:
        r = rows.get(y, {})
        a, b = r.get("raw"), r.get("realistic")
        if not (a and b):
            continue
        mark = "  <-- SEALED 2026, the number that counts" if y == SEALED else ""
        print(f"{y:>6} {a['return_pct']:>+11.2%} {b['return_pct']:>+11.2%} "
              f"{a['max_drawdown']:>7.1%} {b['max_drawdown']:>7.1%} "
              f"{b['trades']:>7}{mark}")

    out = ROOT / "rnd" / f"realism_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(),
        "min_notional": MIN_NOTIONAL, "max_participation": MAX_PARTICIPATION,
        "years": {str(y): rows[y] for y in rows}}, indent=1), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
