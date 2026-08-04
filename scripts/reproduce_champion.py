#!/usr/bin/env python3
from pathlib import Path
"""reproduce_champion.py — reproduce S00743 (volume_climax) en el pipeline
local con los datos reales BTCUSDT ya descargados, como baseline exacto.

Params del champion según el dashboard: volume_window 20, holding ~3,
return_threshold -0.025, volume_multiple 1.5, TP 10.29%, SL 6.36%.
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, "src")

from quantlab.backtest import Backtester, CostModel
from quantlab.config import Settings
from quantlab.data import DataManager
from quantlab.strategies import build_strategy
from quantlab.validation import StatisticalValidator

SETTINGS = Settings.load("config/default.json")
costs = CostModel(
    SETTINGS.commission_bps, SETTINGS.slippage_bps, SETTINGS.funding_bps_per_bar
)

# Cargar datos reales descargados (los guarda el script anterior en data/processed)
manager = DataManager(SETTINGS.data_root, SETTINGS.splits["future_lock_start"])
csv_path = "data/processed/binance/BTCUSDT/1d/81e513286a5ed54f3aeb865fc58c415839c65e3d208c967df5a9eaa05c7ee44b.csv"
if not Path(csv_path).exists():
    from datetime import timezone as _tz
    from quantlab.data import BinanceProvider
    provider = BinanceProvider()
    bars = provider.bars(
        "BTCUSDT", "1d",
        datetime(2017, 8, 17, tzinfo=_tz.utc),
        datetime(2025, 12, 31, tzinfo=_tz.utc),
    )
    manager.validate(bars)
    manager.save_csv(bars, "binance", "BTCUSDT", "1d")
    print(f"[data] descargadas y guardadas {len(bars)} barras", flush=True)
else:
    bars = manager.load_csv(csv_path)
    print(f"[data] {len(bars)} barras cargadas de CSV", flush=True)

champion_params = {
    "volume_window": 20,
    "holding": 3,
    "return_threshold": -0.025,
    "volume_multiple": 1.5,
}

print("=" * 64)
print("S00743 volume_climax · baseline local BTCUSDT 2017-2025")
print("=" * 64)
for label, params in [
    ("S00743 params (volume_climax)", champion_params),
    ("regime_gated defaults", {
        "fit_window": 120, "refit_every": 20, "entry_threshold": 0.55,
        "exit_threshold": 0.45, "min_dwell": 3, "n_states": 3, "seed": 42,
    }),
]:
    strategy = build_strategy(list({"volume_climax", "regime_gated"})[0] if label.startswith("S00743") else "regime_gated", params) if False else None
    family = "volume_climax" if label.startswith("S00743") else "regime_gated"
    strategy = build_strategy(family, params)
    result = Backtester(SETTINGS.initial_equity, costs).run(bars, strategy)
    s = result.summary()
    print(f"\n--- {label} ---")
    print(f"Final equity : ${s['final_equity']:,.2f}")
    print(f"Net return   : {s['net_return']:+.2%}")
    print(f"Max drawdown : {s['drawdown']:.2%}")
    print(f"Sharpe       : {s['sharpe']:.3f}")
    print(f"Profit factor: {s['profit_factor']:.3f}")
    print(f"Trades       : {s.get('trades', 'n/a')}")
    print(f"Exposure     : {s['exposure']:.2%}")
    rob = StatisticalValidator(SETTINGS.minimum_trades).validate(
        result, bars, strategy, SETTINGS.initial_equity, costs
    )
    print(f"Robustness   : {rob['checks']}")
