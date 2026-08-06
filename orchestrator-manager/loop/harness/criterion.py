"""H-015 — if in-sample return is anti-predictive, what should we select on?

H-014R measured the problem: across six configurations, Spearman between
holdout return and 2026 return is -0.371, and residual 2026 alpha falls
monotonically as holdout return rises. Ranking by in-sample return is worse than
useless.

This scores the SAME six configurations under candidate criteria and asks which
ranking would have picked a 2026 winner. It opens nothing: the 2026 numbers are
already on record from H-012 and H-014R, and every criterion below is computed
from holdout data alone.

    python criterion.py

Criteria, all computed from one holdout run per configuration:
  * total return          -- the incumbent, expected to score badly
  * worst rolling 12m     -- stability rather than level
  * monthly return stdev  -- dispersion, lower is better
  * late-bear sub-period  -- score only where the holdout looks like 2026
  * holdout alpha         -- return with exposure x basket return removed
  * return / peak DD      -- risk-adjusted level

The honest caveat, stated here so it reaches the ledger: six pairs is a tiny
sample and the winning criterion is being chosen with the 2026 numbers in hand.
Whatever wins is a PRE-REGISTERED HYPOTHESIS for the next configuration, not a
validated method.
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

db = sqlite3.connect(f"file:{RUNTIME / settings.database_path}?mode=ro", uri=True)
db.row_factory = sqlite3.Row
BARS = {}
for row in db.execute(
    "SELECT symbol,research_path FROM asset_universe "
    "WHERE research_path IS NOT NULL ORDER BY symbol"
):
    bars = [b for b in DataManager.load_csv(row["research_path"]) if b.timestamp < LOCK]
    if len(bars) >= 3:
        BARS[row["symbol"]] = bars


def ref(symbol):
    d = RUNTIME / "data/research/processed/binance" / symbol / "1d"
    f = sorted(d.glob("*.csv"), key=lambda p: p.stat().st_size) if d.is_dir() else []
    return [b for b in DataManager.load_csv(f[-1]) if b.timestamp < LOCK] if f else []


REFS = {s: b for s in REFERENCE_BASKET if (b := ref(s))}
CONTEXT = MarketContext(regimes=build_market_timeline(REFS))
COSTS = CostModel(
    settings.commission_bps, settings.slippage_bps, settings.funding_bps_per_bar
)
FLDS = {f.name for f in dataclasses.fields(MoneyManagement)}
BASE_POLICY = {
    **{k: v for k, v in settings.portfolio.items() if k in FLDS},
    "stop_loss_pct": 0.35,
    "risk_distance_pct": 0.10,
    "maximum_position_fraction": 0.04,
    "maximum_concurrent_assets": 15,
    "drawdown_deleverage_start": 0.25,
}
CAPITAL = float(settings.portfolio["initial_capital"])

BASE_PARAMS = {
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

# The six configurations that already have a 2026 number on record. Nothing new
# is opened; `forward_2026` is quoted from the H-012 and H-014R ledger entries.
CONFIGS = [
    ("market, no stop", {}, {}, -11.04),
    ("market + 2d", {}, {"maximum_holding_days": 2}, -12.57),
    ("asset, no stop", {"regime_scope": "asset"}, {}, -17.41),
    ("asset + 2d", {"regime_scope": "asset"}, {"maximum_holding_days": 2}, -19.97),
    (
        "participation + 2d",
        {"bear_rule": "participation"},
        {"maximum_holding_days": 2},
        -20.73,
    ),
    (
        "cap0.10 w0.6 + 2d",
        {"bear_weight": 0.6},
        # Concurrency must be the CONFIGURED default (12), not a widened one.
        # The first run of this harness passed 100 here while the paired 2026
        # number came from a run at 12, which quietly compared two different
        # strategies and moved this row's holdout return from +443.70% to
        # +626.52%. A criterion comparison is worthless if the pairs are not
        # the same configuration on both sides.
        {
            "maximum_holding_days": 2,
            "maximum_position_fraction": 0.10,
            "maximum_concurrent_assets": 12,
        },
        -13.39,
    ),
]

# 2026 is BEAR from end to end with the composite already deep. The holdout
# sub-period that looks most like it is the back half of the 2022 bear, after
# the first leg down and before the 2023 recovery.
LATE_BEAR = ("2022-06", "2023-01")


def composite_returns() -> dict[str, float]:
    """Equal-weight monthly return of the reference basket, for the beta term."""
    monthly: dict[str, list[float]] = {}
    for bars in REFS.values():
        by_month: dict[str, list[float]] = {}
        for bar in bars:
            if bar.timestamp >= HOLDOUT:
                by_month.setdefault(bar.timestamp.strftime("%Y-%m"), []).append(
                    bar.close
                )
        for month, closes in by_month.items():
            if len(closes) > 1:
                monthly.setdefault(month, []).append(closes[-1] / closes[0] - 1)
    return {m: sum(v) / len(v) for m, v in monthly.items() if v}


BASKET = composite_returns()


def heartbeat() -> None:
    subprocess.run(
        [sys.executable, str(HERE / "bin" / "ledger.py"), "heartbeat"],
        capture_output=True,
    )


def score(label, param_over, policy_over):
    params = {**BASE_PARAMS, **param_over}
    policy = MoneyManagement(**{**BASE_POLICY, **policy_over})
    result = LongOnlyPortfolioBacktester(COSTS, policy).run(
        BARS,
        lambda p=params: build_strategy("regime_router", p, CONTEXT),
        CAPITAL,
        trading_start=HOLDOUT,
    )
    heartbeat()

    curve = [
        p
        for p in result.equity_curve
        if p.get("timestamp", "") >= HOLDOUT.isoformat()[:10]
    ]
    monthly_equity: dict[str, list[float]] = {}
    monthly_expo: dict[str, list[float]] = {}
    for point in curve:
        month = point["timestamp"][:7]
        equity = float(point.get("equity") or 0.0)
        cash = float(point.get("cash") or 0.0)
        monthly_equity.setdefault(month, []).append(equity)
        if equity > 0:
            monthly_expo.setdefault(month, []).append(max(0.0, 1 - cash / equity))

    months = sorted(monthly_equity)
    returns = {}
    for month in months:
        values = monthly_equity[month]
        if len(values) > 1 and values[0] > 0:
            returns[month] = values[-1] / values[0] - 1

    ordered = [returns[m] for m in months if m in returns]
    # Worst rolling twelve months, compounded.
    worst_year = None
    for start in range(0, max(1, len(ordered) - 11)):
        window = ordered[start : start + 12]
        if len(window) < 12:
            continue
        compounded = 1.0
        for r in window:
            compounded *= 1 + r
        worst_year = (
            compounded - 1 if worst_year is None else min(worst_year, compounded - 1)
        )

    mean = sum(ordered) / len(ordered) if ordered else 0.0
    variance = sum((r - mean) ** 2 for r in ordered) / len(ordered) if ordered else 0.0

    late = 1.0
    for month in months:
        if LATE_BEAR[0] <= month <= LATE_BEAR[1] and month in returns:
            late *= 1 + returns[month]

    # Alpha: strip exposure x basket return, month by month, and compound what
    # is left. This is the same decomposition H-014R applied to 2026.
    alpha = 1.0
    for month in months:
        if month not in returns:
            continue
        expo = sum(monthly_expo.get(month, [0.0])) / max(
            1, len(monthly_expo.get(month, [1]))
        )
        alpha *= 1 + (returns[month] - expo * BASKET.get(month, 0.0))

    return {
        "label": label,
        "total_return": result.return_pct,
        "peak_drawdown": result.max_drawdown,
        "capital_drawdown": result.capital_drawdown,
        "average_exposure": result.average_exposure,
        "aborted": result.aborted,
        "worst_rolling_12m": worst_year if worst_year is not None else float("nan"),
        "monthly_stdev": variance**0.5,
        "late_bear_return": late - 1,
        "holdout_alpha": alpha - 1,
        "return_over_drawdown": (
            result.return_pct / result.max_drawdown
            if result.max_drawdown
            else float("nan")
        ),
    }


def spearman(xs, ys):
    def rank(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0] * len(values)
        for position, index in enumerate(order):
            out[index] = position + 1
        return out

    a, b = rank(xs), rank(ys)
    n = len(xs)
    d2 = sum((p - q) ** 2 for p, q in zip(a, b))
    return 1 - 6 * d2 / (n * (n * n - 1))


if __name__ == "__main__":
    print(f"holdout 2022-01-01 .. 2025-12-31, {len(BARS)} assets", flush=True)
    print(f"late-bear sub-period {LATE_BEAR[0]} .. {LATE_BEAR[1]}\n", flush=True)

    rows = []
    for label, param_over, policy_over, forward in CONFIGS:
        row = score(label, param_over, policy_over)
        row["forward_2026"] = forward
        rows.append(row)
        print(
            f"{label:<22} ret {row['total_return']:+9.2%}  worst12m {row['worst_rolling_12m']:+8.2%}  "
            f"stdev {row['monthly_stdev']:6.2%}  lateBear {row['late_bear_return']:+8.2%}  "
            f"alpha {row['holdout_alpha']:+9.2%}  ret/DD {row['return_over_drawdown']:6.2f}  "
            f"| 2026 {forward:+6.2f}%",
            flush=True,
        )

    forward = [r["forward_2026"] for r in rows]
    print("\ncriterion ranked against the 2026 numbers already on record")
    print(f"  {'criterion':<26}{'Spearman vs 2026':>18}")
    for key in (
        "total_return",
        "worst_rolling_12m",
        "monthly_stdev",
        "late_bear_return",
        "holdout_alpha",
        "return_over_drawdown",
    ):
        values = [r[key] for r in rows]
        # Lower dispersion is better, so invert it before ranking.
        if key == "monthly_stdev":
            values = [-v for v in values]
        print(f"  {key:<26}{spearman(values, forward):>+18.3f}")

    Path(HERE / "runs" / "H-015-criterion.json").write_text(json.dumps(rows, indent=2))
