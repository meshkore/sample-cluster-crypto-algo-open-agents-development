#!/usr/bin/env python3
"""sweep_filter.py — pasada 2: sweep de parámetros del filtro HMM sobre V2
(volume_climax + HMM bear-filter) con datos reales BTCUSDT 2017-2025.

Grid: bear_cap x refit_every x fit_window (+ variantes de holding/threshold).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")

from quantlab.backtest import Backtester, CostModel
from quantlab.config import Settings
from quantlab.data import DataManager
from quantlab.hmm_regime import GaussianHMM
from quantlab.validation import StatisticalValidator

SETTINGS = Settings.load("config/default.json")
costs = CostModel(
    SETTINGS.commission_bps, SETTINGS.slippage_bps, SETTINGS.funding_bps_per_bar
)
manager = DataManager(SETTINGS.data_root, SETTINGS.splits["future_lock_start"])
csv = sorted(Path("data/processed/binance/BTCUSDT/1d").glob("*.csv"))[0]
bars = manager.load_csv(str(csv))
print(f"[data] {len(bars)} barras — {csv.name[:12]}", flush=True)


def _mean(values):
    return sum(values) / len(values)


class VolClimaxHmmFilter:
    """volume_climax + HMM bear filter (V2)."""

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
        if post[-1][0] >= bear_cap:
            self.remaining = 0
            return 0.0
        ret = bars[i].close / bars[i - 1].close - 1
        rel_vol = bars[i].volume / _mean([b.volume for b in bars[i - window : i]])
        if ret < float(self.params.get("return_threshold", -0.025)) and rel_vol > float(
            self.params.get("volume_multiple", 1.5)
        ):
            self.remaining = holding
        target = 1.0 if self.remaining > 0 else 0.0
        self.remaining = max(0, self.remaining - 1)
        return target


def run(params):
    strategy = VolClimaxHmmFilter(params)
    result = Backtester(SETTINGS.initial_equity, costs).run(bars, strategy)
    s = result.summary()
    rob = StatisticalValidator(SETTINGS.minimum_trades).validate(
        result, bars, strategy, SETTINGS.initial_equity, costs
    )
    passed = sum(1 for v in rob["checks"].values() if v)
    return {
        "params": params,
        "equity": s["final_equity"],
        "net": s["net_return"],
        "dd": s["drawdown"],
        "sharpe": s["sharpe"],
        "pf": s["profit_factor"],
        "trades": s.get("trades", "n/a"),
        "exposure": s["exposure"],
        "robust": passed,
        "double_cost": rob.get("double_cost_net_return"),
    }


grid = []
for bear_cap in [0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
    for refit in [10, 20, 40]:
        for fit_win in [60, 120, 240]:
            grid.append({
                "volume_window": 20, "holding": 3,
                "return_threshold": -0.025, "volume_multiple": 1.5,
                "fit_window": fit_win, "refit_every": refit,
                "bear_posterior_cap": bear_cap,
            })

print(f"[sweep] {len(grid)} combinaciones\n", flush=True)
results = []
for i, p in enumerate(grid):
    r = run(p)
    results.append(r)
    tag = " ✅" if r["robust"] >= 4 and r["net"] > 0 else ""
    print(f"[{i+1:02d}/{len(grid)}] bear>{p['bear_posterior_cap']:.2f} "
          f"refit={p['refit_every']:02d} fit={p['fit_window']:03d} → "
          f"ret {r['net']:+7.2%} | DD {r['dd']:5.2%} | PF {r['pf']:.2f} | "
          f"Sh {r['sharpe']:.2f} | T {r['trades']} | rob {r['robust']}/5{tag}",
          flush=True)

results.sort(key=lambda r: (r["robust"], r["net"] - r["dd"] * 2), reverse=True)
print("\n=== TOP 8 (por robustez + retorno neto de DD) ===")
for r in results[:8]:
    print(f"  bear>{r['params']['bear_posterior_cap']:.2f} "
          f"refit={r['params']['refit_every']:02d} fit={r['params']['fit_window']:03d} → "
          f"ret {r['net']:+7.2%} | DD {r['dd']:5.2%} | PF {r['pf']:.2f} | "
          f"Sh {r['sharpe']:.2f} | T {r['trades']} | rob {r['robust']}/5 | "
          f"2xcost {r['double_cost']:+.2%}")

out = Path("research/iterations/sweep_filter")
out.mkdir(parents=True, exist_ok=True)
(out / "results.json").write_text(json.dumps(results, indent=1))
print(f"\n[ok] sweep guardado en {out}/results.json")
