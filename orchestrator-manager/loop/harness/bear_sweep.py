"""Pre-2026 selection at the true deployment scope: bear rule and bear gate.

Brackets the two gate thresholds that were set on band boundaries and never
bracketed, and tests the champion's climax mechanism as a bear rule. 2026 is not
read anywhere in this file.
"""

import dataclasses
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RUNTIME = Path.home() / "Library" / "Application Support" / "QuantLab"
REPO = Path(
    "/Users/ricartjuncadella/Documents/Prj/asimovia/other/loop-crypto-algorithm"
)
# Data lives in the runtime copy; CODE comes from the repository working tree.
# The harness must exercise the branch being edited, not the last copy that was
# deployed to the service -- otherwise a change under test is silently absent
# from its own backtest.
sys.path.insert(0, str(RUNTIME / "src"))
sys.path.insert(0, str(REPO / "src"))
os.chdir(RUNTIME)

from quantlab.backtest import CostModel  # noqa: E402
from quantlab.config import Settings  # noqa: E402
from quantlab.data import DataManager  # noqa: E402
from quantlab.portfolio import LongOnlyPortfolioBacktester, MoneyManagement  # noqa: E402
from quantlab.regime import REFERENCE_BASKET, MarketContext, build_market_timeline  # noqa: E402
from quantlab.strategies import build_strategy  # noqa: E402

settings = Settings.load(RUNTIME / "orchestrator-manager" / "config" / "default.json")
LOCK = datetime(2026, 1, 1, tzinfo=timezone.utc)
db = sqlite3.connect(f"file:{RUNTIME / settings.database_path}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

bars_by_symbol = {}
for row in db.execute(
    "SELECT symbol,research_path FROM asset_universe WHERE research_path IS NOT NULL ORDER BY symbol"
):
    bars = [b for b in DataManager.load_csv(row["research_path"]) if b.timestamp < LOCK]
    if len(bars) >= 3:
        bars_by_symbol[row["symbol"]] = bars


def ref(symbol):
    d = RUNTIME / "data/research/processed/binance" / symbol / "1d"
    f = sorted(d.glob("*.csv"), key=lambda p: p.stat().st_size) if d.is_dir() else []
    return [b for b in DataManager.load_csv(f[-1]) if b.timestamp < LOCK] if f else []


timeline = build_market_timeline({s: b for s in REFERENCE_BASKET if (b := ref(s))})
context = MarketContext(regimes=timeline)
print(f"{len(bars_by_symbol)} assets pre-2026", flush=True)

costs = CostModel(
    settings.commission_bps, settings.slippage_bps, settings.funding_bps_per_bar
)
flds = {f.name for f in dataclasses.fields(MoneyManagement)}
policy = MoneyManagement(
    **{
        **{k: v for k, v in settings.portfolio.items() if k in flds},
        "stop_loss_pct": 0.35,
        "risk_distance_pct": 0.10,
        "maximum_position_fraction": 0.10,
    }
)
capital = float(settings.portfolio["initial_capital"])

BASE = {
    "bull_fast_period": 10,
    "bull_slow_period": 30,
    "bull_rsi_period": 14,
    "bull_rsi_floor": 55.0,
    "bull_rsi_ceiling": 90.0,
    "sideways_deviation_period": 25,
    "sideways_entry_deviation": -0.25,
    "sideways_exit_deviation": -0.05,
    "bear_long_period": 200,
    "bear_short_period": 50,
    "bull_weight": 1.0,
    "sideways_weight": 1.0,
    "bear_weight": 0.6,
    "bear_min_depth": 0.70,
    "bear_min_age": 240,
}

CELLS = []
for depth in (0.30, 0.45, 0.55, 0.70, 1.01):
    CELLS.append(
        (f"gate depth={depth:.2f}", {"bear_min_depth": depth, "bear_min_age": 10_000})
    )
for age in (60, 120, 180, 240):
    CELLS.append((f"gate age={age}", {"bear_min_depth": 1.01, "bear_min_age": age}))
for rule in ("climax", "deviation", "breakout", "participation"):
    CELLS.append(
        (
            f"bear_rule={rule} (gate open)",
            {"bear_rule": rule, "bear_min_depth": 0.0, "bear_min_age": 0},
        )
    )
for rule in ("climax", "participation"):
    CELLS.append(
        (
            f"bear_rule={rule} + depth 0.55",
            {"bear_rule": rule, "bear_min_depth": 0.55, "bear_min_age": 10_000},
        )
    )

results = {}
for label, override in CELLS:
    params = {**BASE, **override}
    started = time.monotonic()
    ev = LongOnlyPortfolioBacktester(costs, policy).run(
        bars_by_symbol,
        lambda p=params: build_strategy("regime_router", p, context),
        capital,
    )
    results[label] = {
        "return_pct": ev.return_pct,
        "max_drawdown": ev.max_drawdown,
        "capital_drawdown": ev.capital_drawdown,
        "trades": len(ev.trades),
        "aborted": ev.aborted,
        "last_active": str(ev.last_active_timestamp)[:10],
        "params": override,
    }
    r = results[label]
    print(
        f"{label:34s} ret {r['return_pct']:+10.2%}  peakDD {r['max_drawdown']:6.2%}  "
        f"capDD {r['capital_drawdown']:5.2%}  trades {r['trades']:5d}  "
        f"{'ABORTED' if r['aborted'] else 'legal':8s} last {r['last_active']} "
        f"[{round(time.monotonic() - started)}s]",
        flush=True,
    )

legal = {k: v for k, v in results.items() if not v["aborted"]}
best = max(legal, key=lambda k: legal[k]["return_pct"])
print(f"\nBEST LEGAL (pre-2026): {best} -> {legal[best]['return_pct']:+.2%}")
Path("/tmp/bear_sweep.json").write_text(json.dumps(results, indent=2))
