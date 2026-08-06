"""Portfolio evaluation on the pre-2026 BEAR HOLDOUT (2022-01-01 .. 2025-12-31).

Selection may iterate here as often as it likes: this window is inside the
training era as far as the 2026 lock is concerned, but it was never used to fit
any parameter until now, and it contains a full bear market. 2026 is not opened.

Usage: python holdout_loop.py '<json overrides>' ['<label>']
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
HOLDOUT = datetime(2022, 1, 1, tzinfo=timezone.utc)

db = sqlite3.connect(f"file:{RUNTIME / settings.database_path}?mode=ro", uri=True)
db.row_factory = sqlite3.Row
BARS = {}
for row in db.execute(
    "SELECT symbol,research_path,forward_path FROM asset_universe WHERE research_path IS NOT NULL ORDER BY symbol"
):
    hist = [b for b in DataManager.load_csv(row["research_path"]) if b.timestamp < LOCK]
    fwd = []
    if row["forward_path"]:
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
    d2 = RUNTIME / "data/forward/processed/binance" / symbol / "1d"
    f2 = sorted(d2.glob("*.csv"), key=lambda p: p.stat().st_size) if d2.is_dir() else []
    fwd = [b for b in DataManager.load_csv(f2[-1]) if b.timestamp >= LOCK] if f2 else []
    return hist + fwd


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
        "maximum_position_fraction": 0.10,
    }
)
CAPITAL = float(settings.portfolio["initial_capital"])

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
    "bear_max_below_high": 0.60,
    "bull_weight": 1.0,
    "sideways_weight": 1.0,
    "bear_weight": 0.6,
    "bear_min_depth": 0.0,
    "bear_min_age": 0,
}


def run(label, overrides, start=HOLDOUT):
    pol_over = {k[8:]: v for k, v in overrides.items() if k.startswith("_policy_")}
    params = {
        **BASE,
        **{k: v for k, v in overrides.items() if not k.startswith("_policy_")},
    }
    policy = POLICY if not pol_over else dataclasses.replace(POLICY, **pol_over)
    t0 = time.monotonic()
    ev = LongOnlyPortfolioBacktester(COSTS, policy).run(
        BARS,
        lambda p=params: build_strategy("regime_router", p, CONTEXT),
        CAPITAL,
        trading_start=start,
    )
    print(
        f"{label:38s} ret {ev.return_pct:+9.2%}  peakDD {ev.max_drawdown:6.2%}  "
        f"capDD {ev.capital_drawdown:5.2%}  trades {len(ev.trades):5d}  "
        f"expo {ev.average_exposure:5.2%}  "
        f"{'ABORTED' if ev.aborted else 'legal':8s}[{round(time.monotonic() - t0)}s]",
        flush=True,
    )
    return ev


if __name__ == "__main__":
    cells = json.loads(sys.argv[1])
    print(f"FORWARD 2026 -- sealed until now. {len(BARS)} assets\n", flush=True)
    for label, ov in cells:
        run(label, ov, start=LOCK)
