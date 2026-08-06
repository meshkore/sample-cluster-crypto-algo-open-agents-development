"""H-016 — is +30% in 2026 reachable at all with the entries we generate?

Every iteration so far has asked "can this configuration do better". None has
asked "what is the ceiling". After H-015 established that we cannot validate a
selection rule from one forward window, the useful question is no longer which
configuration to pick but whether the target is inside the feasible set.

This measures three bounds on the SAME trades our system already opened, using
the 2026 run that H-010 opened and H-011 decomposed. It fits nothing, tunes
nothing, and proposes no strategy. It uses hindsight ON PURPOSE, to bound what
hindsight is worth:

  1. ACTUAL         -- what the run returned.
  2. PERFECT EXIT   -- every trade closed at its maximum favourable excursion.
                       The ceiling on all possible exit work, given these entries.
  3. NO LOSERS      -- every losing trade skipped, winners held as they were.
                       The ceiling on all possible entry FILTERING, given these
                       entries.

If perfect exits cannot reach the target, no amount of exit engineering will,
and the entries themselves have to change. That is a decision, not a number.

    python feasibility.py [window]      window = 2026 (default) | holdout

Returns are reported as summed trade PnL over initial capital, un-compounded, so
the bound and the actual are computed the same way and stay comparable. They
will not equal the compounded figures quoted elsewhere.
"""

import dataclasses
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RUNTIME = Path.home() / "Library" / "Application Support" / "QuantLab"
REPO = Path(
    "/Users/ricartjuncadella/Documents/Prj/asimovia/other/loop-crypto-algorithm"
)
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
HOLDOUT = datetime(2022, 1, 1, tzinfo=timezone.utc)
HERE = Path(__file__).parent.parent
WINDOW = sys.argv[1] if len(sys.argv) > 1 else "2026"
START = LOCK if WINDOW == "2026" else HOLDOUT

db = sqlite3.connect(f"file:{RUNTIME / settings.database_path}?mode=ro", uri=True)
db.row_factory = sqlite3.Row
BARS = {}
for row in db.execute(
    "SELECT symbol,research_path,forward_path FROM asset_universe "
    "WHERE research_path IS NOT NULL ORDER BY symbol"
):
    hist = [b for b in DataManager.load_csv(row["research_path"]) if b.timestamp < LOCK]
    fwd = []
    if row["forward_path"] and WINDOW == "2026":
        fwd = [
            b for b in DataManager.load_csv(row["forward_path"]) if b.timestamp >= LOCK
        ]
    bars = hist + fwd
    if len(bars) >= 3:
        BARS[row["symbol"]] = bars


def ref(symbol):
    d = RUNTIME / "data/research/processed/binance" / symbol / "1d"
    f = sorted(d.glob("*.csv"), key=lambda p: p.stat().st_size) if d.is_dir() else []
    hist = [b for b in DataManager.load_csv(f[-1]) if b.timestamp < LOCK] if f else []
    if WINDOW != "2026":
        return hist
    d2 = RUNTIME / "data/forward/processed/binance" / symbol / "1d"
    f2 = sorted(d2.glob("*.csv"), key=lambda p: p.stat().st_size) if d2.is_dir() else []
    return hist + (
        [b for b in DataManager.load_csv(f2[-1]) if b.timestamp >= LOCK] if f2 else []
    )


CONTEXT = MarketContext(
    regimes=build_market_timeline({s: b for s in REFERENCE_BASKET if (b := ref(s))})
)
COSTS = CostModel(
    settings.commission_bps, settings.slippage_bps, settings.funding_bps_per_bar
)
FLDS = {f.name for f in dataclasses.fields(MoneyManagement)}
POLICY = MoneyManagement(
    **{
        **{k: v for k, v in settings.portfolio.items() if k in FLDS},
        "stop_loss_pct": 0.35,
        "risk_distance_pct": 0.10,
        "maximum_position_fraction": 0.04,
        "maximum_concurrent_assets": 15,
        "drawdown_deleverage_start": 0.25,
    }
)
CAPITAL = float(settings.portfolio["initial_capital"])
PARAMS = {
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
    "bear_max_below_high": 0.60,
    "bull_weight": 1.0,
    "sideways_weight": 1.0,
    "bear_weight": 1.0,
    "bear_rule": "breakout",
    "bear_min_depth": 0.0,
    "bear_min_age": 0,
}

print(f"window {WINDOW}  start {START.date()}  assets {len(BARS)}", flush=True)
result = LongOnlyPortfolioBacktester(COSTS, POLICY).run(
    BARS,
    lambda: build_strategy("regime_router", PARAMS, CONTEXT),
    CAPITAL,
    trading_start=START,
)
subprocess.run(
    [sys.executable, str(HERE / "bin" / "ledger.py"), "heartbeat"], capture_output=True
)
trades = [t for t in result.trades if t.exit_time >= START]
print(
    f"compounded return {result.return_pct:+.2%}   trades {len(trades)}\n", flush=True
)

# Per-trade excursions, from the bars the trade actually lived through.
rows = []
for trade in trades:
    series = BARS.get(trade.symbol) or []
    inside = [b for b in series if trade.entry_time <= b.timestamp <= trade.exit_time]
    if not inside:
        continue
    best = max(b.high for b in inside)
    worst = min(b.low for b in inside)
    rows.append(
        {
            "pnl": trade.pnl,
            "invested": trade.invested_capital,
            "realised_pct": trade.pnl_pct,
            "mfe_pct": best / trade.entry_price - 1,
            "mae_pct": worst / trade.entry_price - 1,
            "reason": trade.exit_reason,
        }
    )

actual = sum(r["pnl"] for r in rows)
# Costs are already inside `pnl`; approximate them for the counterfactuals as
# the same round-trip fraction the realised trade paid.
perfect_exit = sum(r["invested"] * r["mfe_pct"] for r in rows)
no_losers = sum(r["pnl"] for r in rows if r["pnl"] > 0)
target_capped = sum(
    r["invested"] * min(r["mfe_pct"], POLICY.take_profit_pct) for r in rows
)


def pct(value):
    return value / CAPITAL


ordered = sorted(r["mfe_pct"] for r in rows)
median_mfe = ordered[len(ordered) // 2] if ordered else 0.0
reached_target = sum(1 for r in rows if r["mfe_pct"] >= POLICY.take_profit_pct)

print(f"{'bound':<38}{'summed PnL':>14}{'over capital':>14}")
print(f"{'ACTUAL (what we got)':<38}{actual:>14,.0f}{pct(actual):>13.2%}")
print(
    f"{'NO LOSERS (perfect entry filter)':<38}{no_losers:>14,.0f}{pct(no_losers):>13.2%}"
)
print(
    f"{'EXIT AT TARGET WHERE REACHABLE':<38}{target_capped:>14,.0f}{pct(target_capped):>13.2%}"
)
print(
    f"{'PERFECT EXIT (exit at the high)':<38}{perfect_exit:>14,.0f}{pct(perfect_exit):>13.2%}"
)

print(f"\nexcursions over {len(rows)} trades")
print(f"  median MFE                    {median_mfe:+.2%}")
print(
    f"  mean MFE                      {sum(r['mfe_pct'] for r in rows) / len(rows):+.2%}"
)
print(
    f"  mean MAE                      {sum(r['mae_pct'] for r in rows) / len(rows):+.2%}"
)
print(
    f"  reached the {POLICY.take_profit_pct:.0%} target        "
    f"{reached_target}/{len(rows)} = {reached_target / len(rows):.0%}"
)
print(
    f"  gave back (MFE minus realised) {sum(r['mfe_pct'] - r['realised_pct'] for r in rows) / len(rows):+.2%} per trade"
)

Path(HERE / "runs" / f"H-016-feasibility-{WINDOW}.json").write_text(
    json.dumps(
        {
            "window": WINDOW,
            "compounded_return": result.return_pct,
            "trades": len(rows),
            "actual_over_capital": pct(actual),
            "no_losers_over_capital": pct(no_losers),
            "target_capped_over_capital": pct(target_capped),
            "perfect_exit_over_capital": pct(perfect_exit),
            "median_mfe": median_mfe,
            "reached_target_share": reached_target / len(rows) if rows else 0.0,
        },
        indent=2,
    )
)
