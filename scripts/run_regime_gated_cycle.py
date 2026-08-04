#!/usr/bin/env python3
"""run_regime_gated_cycle.py — ejecuta H-REGIME-001 con el pipeline oficial del lab.

Usa las mismas piezas que ResearchDirector (Backtester, StatisticalValidator,
AdversarialCritic, SyntheticProvider) forzando la familia regime_gated, y
escribe el reporte de iteración como lo haría el loop.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")

from quantlab.backtest import Backtester, CostModel
from quantlab.config import Settings
from quantlab.data import SyntheticProvider
from quantlab.strategies import build_strategy, initial_hypotheses
from quantlab.validation import AdversarialCritic, StatisticalValidator

SETTINGS = Settings.load("config/default.json")

hyp = next(h for h in initial_hypotheses("transfer") if h.id == "H-REGIME-001")
params = {
    "fit_window": 120,
    "refit_every": 20,
    "entry_threshold": 0.55,
    "exit_threshold": 0.45,
    "min_dwell": 3,
    "n_states": 3,
    "seed": 42,
    "lineage_generation": 0,
}
costs = CostModel(
    SETTINGS.commission_bps, SETTINGS.slippage_bps, SETTINGS.funding_bps_per_bar
)

bars = SyntheticProvider(SETTINGS.seed).bars(
    "BTCUSDT",
    "1d",
    datetime(2021, 1, 1, tzinfo=timezone.utc),
    datetime(2024, 1, 1, tzinfo=timezone.utc),
)

strategy = build_strategy("regime_gated", params)
result = Backtester(SETTINGS.initial_equity, costs).run(bars, strategy)
summary = result.summary()
robustness = StatisticalValidator(SETTINGS.minimum_trades).validate(
    result, bars, strategy, SETTINGS.initial_equity, costs
)
critic = AdversarialCritic().critique(hyp, result, robustness, True)

print("=" * 60)
print("H-REGIME-001 · regime_gated · pipeline oficial del lab")
print("=" * 60)
print(f"Final equity : ${summary['final_equity']:,.2f}")
print(f"Net return   : {summary['net_return']:+.2%}")
print(f"Max drawdown : {summary['drawdown']:.2%}")
print(f"Sharpe       : {summary['sharpe']:.3f}")
print(f"Profit factor: {summary['profit_factor']:.3f}")
print(f"Trades       : {summary.get('trades', 'n/a')}")
print(f"Exposure     : {summary['exposure']:.2%}")
print()
print("--- Robustness ---")
print(json.dumps(robustness, indent=1)[:600])
print()
print("--- Critic verdict ---")
print(f"verdict: {critic['verdict']}")
print(f"confidence: {critic['confidence']}")
for f in critic.get("critical_failures", [])[:3]:
    print(f"  FAIL: {f}")

out = Path("research/iterations/regime_gated_demo")
out.mkdir(parents=True, exist_ok=True)
(out / "results.json").write_text(json.dumps(summary, indent=1))
(out / "robustness.json").write_text(json.dumps(robustness, indent=1))
(out / "critique.json").write_text(json.dumps(critic, indent=1))
print(f"\nReporte escrito en {out}")
