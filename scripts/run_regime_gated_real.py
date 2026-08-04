#!/usr/bin/env python3
"""run_regime_gated_real.py — H-REGIME-001 con DATOS REALES de Binance.

Descarga BTCUSDT 1d (2017-2025, el rango del dashboard del lab), valida con
el DataManager (futuro 2026 bloqueado), y corre el pipeline oficial del lab
(Backtester + StatisticalValidator + AdversarialCritic).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")

from quantlab.backtest import Backtester, CostModel
from quantlab.config import Settings
from quantlab.data import BinanceProvider, DataManager
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

start = datetime(2017, 8, 17, tzinfo=timezone.utc)   # inicio del dashboard del lab
end = datetime(2025, 12, 31, tzinfo=timezone.utc)    # fin antes del lock 2026

print("[data] Descargando BTCUSDT 1d desde Binance (2017-2025)...", flush=True)
provider = BinanceProvider()
bars = provider.bars("BTCUSDT", "1d", start, end)
print(f"[data] {len(bars)} barras descargadas", flush=True)

manager = DataManager(SETTINGS.data_root, SETTINGS.splits["future_lock_start"])
manager.validate(bars)
version = manager.version(bars, "binance", "BTCUSDT", "1d")
print(f"[data] validado OK — dataset {version[:12]}", flush=True)

out = Path("research/iterations/regime_gated_real")
out.mkdir(parents=True, exist_ok=True)
(out / "dataset.txt").write_text(f"symbol=BTCUSDT interval=1d range={start.date()}..{end.date()} bars={len(bars)} version={version}\n")

strategy = build_strategy("regime_gated", params)
result = Backtester(SETTINGS.initial_equity, costs).run(bars, strategy)
summary = result.summary()
robustness = StatisticalValidator(SETTINGS.minimum_trades).validate(
    result, bars, strategy, SETTINGS.initial_equity, costs
)
critic = AdversarialCritic().critique(hyp, result, robustness, True)

print("=" * 64)
print("H-REGIME-001 · DATOS REALES Binance BTCUSDT 1d (2017-2025)")
print("=" * 64)
print(f"Final equity : ${summary['final_equity']:,.2f}")
print(f"Net return   : {summary['net_return']:+.2%}")
print(f"Max drawdown : {summary['drawdown']:.2%}")
print(f"Sharpe       : {summary['sharpe']:.3f}")
print(f"Profit factor: {summary['profit_factor']:.3f}")
print(f"Trades       : {summary.get('trades', 'n/a')}")
print(f"Exposure     : {summary['exposure']:.2%}")
print()
print("--- Robustness ---")
for check, ok in robustness["checks"].items():
    print(f"  {check}: {ok}")
print(f"  double_cost_net_return: {robustness.get('double_cost_net_return'):+.2%}")
print()
print("--- Critic ---")
print(f"  verdict: {critic['verdict']} | confidence: {critic['confidence']}")
for f in critic.get("critical_failures", [])[:3]:
    print(f"  FAIL: {f}")

(out / "results.json").write_text(json.dumps(summary, indent=1))
(out / "robustness.json").write_text(json.dumps(robustness, indent=1))
(out / "critique.json").write_text(json.dumps(critic, indent=1))
print(f"\nReporte guardado en {out}")
