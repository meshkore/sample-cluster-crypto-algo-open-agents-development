#!/usr/bin/env python3
"""battle_strategies.py — batalla de variantes contra el champion en BTCUSDT real.

V1 = champion puro (volume_climax) — baseline
V2 = volume_climax + filtro HMM (no operar en bear persistente)
V3 = volume_climax + filtro HMM suave (no operar en bear) + TP/SL asimétrico
V4 = HMM regime_gated relajado (posterior 0.45, dwell 2)
V5 = HMM regime_gated relajado + TP/SL asimétrico (10%/6.4%)
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")

from quantlab.backtest import Backtester, CostModel
from quantlab.config import Settings
from quantlab.data import DataManager
from quantlab.hmm_regime import GaussianHMM, declare_regimes
from quantlab.strategies import build_strategy
from quantlab.validation import StatisticalValidator

SETTINGS = Settings.load("config/default.json")
costs = CostModel(
    SETTINGS.commission_bps, SETTINGS.slippage_bps, SETTINGS.funding_bps_per_bar
)
manager = DataManager(SETTINGS.data_root, SETTINGS.splits["future_lock_start"])
bars = manager.load_csv("data/processed/binance/BTCUSDT/1d/81e513286a5ed54f3aeb865fc58c415839c65e3d208c967df5a9eaa05c7ee44b.csv")
print(f"[data] {len(bars)} barras", flush=True)


class VolumeClimaxRegimeFiltered:
    """volume_climax + HMM regime filter: no long entries while the smoothed
    bear posterior dominates (bear >= 0.5), so the reversal is only traded
    in non-persistent-bear tape."""

    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self):
        self.remaining = 0
        self._model = None
        self._last_fit = 0

    def on_bar(self, bars):
        window = int(self.params.get("volume_window", 20))
        holding = int(self.params.get("holding", 3))
        fit_window = int(self.params.get("fit_window", 120))
        refit_every = int(self.params.get("refit_every", 20))
        bear_cap = float(self.params.get("bear_posterior_cap", 0.5))
        i = len(bars) - 1
        if i < max(window, fit_window):
            return 0.0
        closes = [b.close for b in bars[i - fit_window + 1 : i + 1]]
        if self._model is None or (i - self._last_fit) >= refit_every:
            model = GaussianHMM(n_states=3, seed=42).fit(closes)
            self._model = model.sorted_by_mean()
            self._last_fit = i
        post = self._model.posterior(closes)
        bear = post[-1][0]  # index 0 = lowest mean state after sorting
        if bear >= bear_cap:
            self.remaining = 0
            return 0.0  # persistent bear: abstain entirely
        ret = bars[i].close / bars[i - 1].close - 1
        rel_vol = bars[i].volume / _mean([b.volume for b in bars[i - window : i]])
        if ret < float(self.params.get("return_threshold", -0.025)) and rel_vol > float(
            self.params.get("volume_multiple", 1.5)
        ):
            self.remaining = holding
        target = 1.0 if self.remaining > 0 else 0.0
        self.remaining = max(0, self.remaining - 1)
        return target


def _mean(values):
    return sum(values) / len(values)


class RegimeGatedRelaxed:
    """regime_gated con gate relajado (0.45, dwell 2) — señal continua bull posterior."""

    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self):
        self._model = None
        self._last_fit = 0
        self._dwell = 0

    def on_bar(self, bars):
        fit_window = int(self.params.get("fit_window", 120))
        refit_every = int(self.params.get("refit_every", 20))
        entry = float(self.params.get("entry_threshold", 0.45))
        exit_t = float(self.params.get("exit_threshold", 0.40))
        min_dwell = int(self.params.get("min_dwell", 2))
        i = len(bars) - 1
        if i < fit_window:
            return 0.0
        closes = [b.close for b in bars[i - fit_window + 1 : i + 1]]
        if self._model is None or (i - self._last_fit) >= refit_every:
            model = GaussianHMM(n_states=3, seed=42).fit(closes)
            self._model = model.sorted_by_mean()
            self._last_fit = i
        post = self._model.posterior(closes)
        bull = post[-1][2]
        if bull >= exit_t:
            self._dwell += 1
        else:
            self._dwell = 0
        if self._dwell < min_dwell or bull < entry:
            return 0.0
        return min(1.0, bull)


def run(label, strategy, note=""):
    result = Backtester(SETTINGS.initial_equity, costs).run(bars, strategy)
    s = result.summary()
    rob = StatisticalValidator(SETTINGS.minimum_trades).validate(
        result, bars, strategy, SETTINGS.initial_equity, costs
    )
    passed = sum(1 for v in rob["checks"].values() if v)
    print(f"\n--- {label} {note} ---")
    print(f"Equity ${s['final_equity']:,.0f} | Ret {s['net_return']:+.2%} | "
          f"DD {s['drawdown']:.2%} | Sharpe {s['sharpe']:.2f} | PF {s['profit_factor']:.2f} | "
          f"Trades {s.get('trades','n/a')} | Exp {s['exposure']:.1%}")
    print(f"Robustness {passed}/5: {rob['checks']}")
    return s, rob


print("=" * 70)
print("BATALLA DE VARIANTES · BTCUSDT real 2017-2025")
print("=" * 70)

# V1 champion
champion = build_strategy("volume_climax", {
    "volume_window": 20, "holding": 3,
    "return_threshold": -0.025, "volume_multiple": 1.5,
})
run("V1 champion volume_climax", champion)

# V2 volume_climax + HMM bear filter
v2 = VolumeClimaxRegimeFiltered({
    "volume_window": 20, "holding": 3, "return_threshold": -0.025,
    "volume_multiple": 1.5, "fit_window": 120, "refit_every": 20,
    "bear_posterior_cap": 0.5,
})
run("V2 vol_climax + HMM bear-filter", v2)

# V3 vol_climax + bear filter + TP/SL (el Backtester no aplica TP/SL: probamos con hold más corto)
v3 = VolumeClimaxRegimeFiltered({
    "volume_window": 20, "holding": 2, "return_threshold": -0.03,
    "volume_multiple": 1.5, "fit_window": 120, "refit_every": 20,
    "bear_posterior_cap": 0.45,
})
run("V3 vol_climax + filtro + hold 2", v3)

# V4 regime_gated relajado
v4 = RegimeGatedRelaxed({
    "fit_window": 120, "refit_every": 20, "entry_threshold": 0.45,
    "exit_threshold": 0.40, "min_dwell": 2,
})
run("V4 HMM relajado 0.45/dwell2", v4)

# V5 HMM relajado + volumen (solo bull)
class HmmBullVolume(RegimeGatedRelaxed):
    def on_bar(self, bars):
        base = super().on_bar(bars)
        if base <= 0.0:
            return 0.0
        window = int(self.params.get("volume_window", 20))
        i = len(bars) - 1
        if i < window:
            return 0.0
        rel_vol = bars[i].volume / _mean([b.volume for b in bars[i - window : i]])
        return base if rel_vol > float(self.params.get("volume_multiple", 1.0)) else 0.0

v5 = HmmBullVolume({
    "fit_window": 120, "refit_every": 20, "entry_threshold": 0.45,
    "exit_threshold": 0.40, "min_dwell": 2, "volume_window": 20,
    "volume_multiple": 1.0,
})
run("V5 HMM bull + confirmación volumen", v5)

# Guardar resultados
out = Path("research/iterations/battle_real")
out.mkdir(parents=True, exist_ok=True)
(out / "summary.txt").write_text("batalla de variantes completada\n")
print("\n[ok] batalla completada")
