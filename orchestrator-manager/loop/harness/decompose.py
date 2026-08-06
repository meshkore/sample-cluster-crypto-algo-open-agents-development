"""H-011 — the anatomy of the 2026 loss.

We know the number (-11.04%) and nothing about its shape. Before designing
another entry rule, find out whether the money is lost on entries, on exits, on
sizing, or on being in the market at all.

This re-runs a configuration that has ALREADY been opened on 2026 (H-010) and
reads its trade list. It introduces no new selection and no new look: the run
is on record, and refusing to inspect a result we already paid for would be
superstition rather than discipline. Nothing here tunes a parameter.

    python decompose.py [window]      window = 2026 (default) | holdout

Prints:
  * exit anatomy      -- stop-out versus signal exit, and the PnL of each
  * holding period    -- are we clipped early, or bleeding slowly?
  * month by month    -- exposure and PnL, so a single bad month is visible
  * per asset         -- is the loss broad or three names?
  * the nulls         -- cash, and buy-and-hold on the reference composite
"""

import dataclasses
import json
import os
import sqlite3
import sys
from collections import defaultdict
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
HOLDOUT = datetime(2022, 1, 1, tzinfo=timezone.utc)
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


REFS = {s: b for s in REFERENCE_BASKET if (b := ref(s))}
CONTEXT = MarketContext(regimes=build_market_timeline(REFS))
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
    }
)
CAPITAL = float(settings.portfolio["initial_capital"])

# The H-010 configuration: best legal holdout result, already opened on 2026.
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

print(f"window {WINDOW}  start {START.date()}  assets {len(BARS)}\n", flush=True)
ev = LongOnlyPortfolioBacktester(COSTS, POLICY).run(
    BARS,
    lambda: build_strategy("regime_router", PARAMS, CONTEXT),
    CAPITAL,
    trading_start=START,
)

print(
    f"return {ev.return_pct:+.2%}   capital drawdown {ev.capital_drawdown:.2%}   "
    f"trades {len(ev.trades)}   exposure avg {ev.average_exposure:.2%} "
    f"peak {ev.peak_exposure:.2%}  time in market {ev.time_in_market:.2%}   "
    f"{'ABORTED' if ev.aborted else 'legal'}\n"
)

trades = [t for t in ev.trades if t.exit_time >= START]

# --- exit anatomy ---------------------------------------------------------- #
by_reason = defaultdict(lambda: [0, 0.0, 0])
for t in trades:
    e = by_reason[t.exit_reason]
    e[0] += 1
    e[1] += t.pnl
    e[2] += t.pnl > 0
print("exit anatomy")
print(f"  {'reason':<18}{'n':>7}{'pnl usd':>14}{'win rate':>10}{'avg pnl%':>10}")
for reason, (n, pnl, wins) in sorted(by_reason.items(), key=lambda kv: kv[1][1]):
    avg = sum(t.pnl_pct for t in trades if t.exit_reason == reason) / n
    print(f"  {reason:<18}{n:>7}{pnl:>14,.0f}{wins / n:>10.0%}{avg:>10.2%}")

# --- holding period -------------------------------------------------------- #
print("\nholding period")
buckets = [(0, 3), (3, 7), (7, 21), (21, 60), (60, 10_000)]
for lo, hi in buckets:
    sel = [t for t in trades if lo <= t.duration_seconds / 86400 < hi]
    if not sel:
        continue
    pnl = sum(t.pnl for t in sel)
    wins = sum(1 for t in sel if t.pnl > 0)
    label = f"{lo}-{hi}d" if hi < 10_000 else f"{lo}d+"
    print(f"  {label:<10}{len(sel):>7}{pnl:>14,.0f}{wins / len(sel):>10.0%}")

# --- month by month -------------------------------------------------------- #
print("\nmonth by month")
monthly_pnl = defaultdict(float)
monthly_n = defaultdict(int)
for t in trades:
    key = t.exit_time.strftime("%Y-%m")
    monthly_pnl[key] += t.pnl
    monthly_n[key] += 1
# The equity curve carries cash and marked equity, not an exposure field, so
# the invested fraction has to be derived. Reading a missing key as zero is how
# the first run of this script reported 0.0% exposure in every month against a
# 21.22% average.
expo = defaultdict(list)
for point in ev.equity_curve:
    stamp = point.get("timestamp", "")
    if stamp and stamp >= START.isoformat()[:10]:
        equity = float(point.get("equity") or 0.0)
        cash = float(point.get("cash") or 0.0)
        if equity > 0:
            expo[stamp[:7]].append(max(0.0, 1 - cash / equity))
for key in sorted(set(monthly_pnl) | set(expo)):
    e = expo.get(key, [])
    print(
        f"  {key}  trades {monthly_n.get(key, 0):>5}  pnl {monthly_pnl.get(key, 0.0):>+12,.0f}  "
        f"exposure {sum(e) / len(e) if e else 0:.1%}"
    )

# --- per asset ------------------------------------------------------------- #
per_asset = defaultdict(float)
for t in trades:
    per_asset[t.symbol] += t.pnl
ranked = sorted(per_asset.items(), key=lambda kv: kv[1])
print(f"\nper asset ({len(per_asset)} traded)")
print("  worst: " + ", ".join(f"{s} {p:+,.0f}" for s, p in ranked[:6]))
print("  best : " + ", ".join(f"{s} {p:+,.0f}" for s, p in ranked[-6:][::-1]))
losers = sum(p for _, p in ranked if p < 0)
winners = sum(p for _, p in ranked if p > 0)
print(
    f"  gross winners {winners:+,.0f}   gross losers {losers:+,.0f}   "
    f"net {winners + losers:+,.0f}"
)

# --- the nulls ------------------------------------------------------------- #
print("\nnulls over the same window")
print(f"  cash                     {0.0:+.2%}")
for sym, bars in sorted(REFS.items()):
    inside = [b for b in bars if b.timestamp >= START]
    if len(inside) > 2:
        print(f"  buy and hold {sym:<12}{inside[-1].close / inside[0].close - 1:+.2%}")

Path("/tmp/decompose.json").write_text(
    json.dumps(
        {
            "window": WINDOW,
            "return_pct": ev.return_pct,
            "capital_drawdown": ev.capital_drawdown,
            "trades": len(trades),
            "average_exposure": ev.average_exposure,
            "time_in_market": ev.time_in_market,
            "aborted": ev.aborted,
            "by_reason": {
                k: {"n": v[0], "pnl": v[1], "wins": v[2]} for k, v in by_reason.items()
            },
            "gross_winners": winners,
            "gross_losers": losers,
        },
        indent=2,
    )
)
