#!/usr/bin/env python3
"""forward_sweep.py — pasada 4: sweep bear_cap + sizing adaptativo HMM.

Para cada bear_cap {0.50, 0.55, 0.60, 0.65}:
  A) Filtro fijo (gate 0/1) — baseline
  B) Sizing adaptativo (position = target_vol / state_vol) — señal continua

Reporta: histórico completo (2017-2026) + solo 2026 (forward).
"""
import json, sys, math
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")

from quantlab.backtest import Backtester, CostModel
from quantlab.config import Settings
from quantlab.data import DataManager
from quantlab.hmm_regime import GaussianHMM

SETTINGS = Settings.load("config/default.json")
costs = CostModel(SETTINGS.commission_bps, SETTINGS.slippage_bps, SETTINGS.funding_bps_per_bar)
manager = DataManager(SETTINGS.data_root, SETTINGS.splits["future_lock_start"])
LOCK = datetime.fromisoformat(SETTINGS.splits["future_lock_start"].replace("Z", "+00:00"))

# Cargar datos
hist = manager.load_csv(str(sorted(Path("data/processed/binance/BTCUSDT/1d").glob("*.csv"))[0]))
hist = [b for b in hist if b.timestamp < LOCK]
fwd = manager.load_csv(str(Path("data/processed/binance/BTCUSDT/1d/forward_2026.csv")))
fwd = [b for b in fwd if b.timestamp >= LOCK]
combined = {b.timestamp: b for b in hist}
combined.update({b.timestamp: b for b in fwd})
bars_all = [combined[k] for k in sorted(combined)]
bars_2026 = [b for b in bars_all if b.timestamp >= LOCK]
print(f"[data] hist {len(hist)} + fwd {len(fwd)} = {len(bars_all)} total | 2026: {len(bars_2026)}", flush=True)

def _mean(v): return sum(v) / len(v)


class VolClimaxHmmSizing:
    """volume_climax + HMM. Modos:
    - gate: abstener si bear >= bear_cap (0/1 signal)
    - sizing: señal continua = clamp(target_vol / state_vol, 0, 1)
      donde state_vol es la varianza del estado dominante actual.
    Si bear >= hard_block (0.70), abstener totalmente.
    """
    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self):
        self.remaining = 0
        self._model = None
        self._last_fit = -10**9

    def on_bar(self, bars):
        window = int(self.params.get("volume_window", 20))
        holding = int(self.params.get("holding", 3))
        fit_window = int(self.params.get("fit_window", 120))
        refit_every = int(self.params.get("refit_every", 20))
        bear_cap = float(self.params.get("bear_posterior_cap", 0.50))
        hard_block = float(self.params.get("hard_block", 0.70))
        mode = self.params.get("mode", "gate")
        target_vol = float(self.params.get("target_vol", 0.02))  # 2% daily vol target
        i = len(bars) - 1
        if i < max(window, fit_window):
            return 0.0
        closes = [b.close for b in bars[i - fit_window + 1 : i + 1]]
        if self._model is None or (i - self._last_fit) >= refit_every:
            m = GaussianHMM(n_states=3, seed=42).fit(closes)
            self._model = m.sorted_by_mean()
            self._last_fit = i
            self._state_vols = [math.sqrt(max(v, 1e-10)) for v in self._model.vars]
        post = self._model.posterior(closes)
        p = post[-1]
        bear = p[0]

        if bear >= hard_block:
            self.remaining = 0
            return 0.0

        ret = bars[i].close / bars[i - 1].close - 1
        rel_vol = bars[i].volume / _mean([b.volume for b in bars[i - window : i]])

        if ret < float(self.params.get("return_threshold", -0.025)) and rel_vol > float(
            self.params.get("volume_multiple", 1.5)
        ):
            self.remaining = holding

        if self.remaining <= 0:
            return 0.0

        self.remaining = max(0, self.remaining - 1)

        if mode == "gate":
            if bear >= bear_cap:
                self.remaining = 0
                return 0.0
            return 1.0
        else:  # sizing adaptativo
            # Vol del estado dominante
            dom_state = max(range(3), key=lambda s: p[s])
            sv = self._state_vols[dom_state]
            # Scalar por bear: a más bear, menos size
            bear_penalty = max(0.0, 1.0 - bear * 1.5)
            # Size = target_vol / state_vol, capped [0.15, 1.0]
            raw = target_vol / sv if sv > 1e-8 else 1.0
            size = max(0.15, min(1.0, raw)) * bear_penalty
            if bear >= bear_cap:
                size *= 0.5  # no cortar, reducir a la mitad
            return size


def run(label, bars, params):
    strategy = VolClimaxHmmSizing(params)
    result = Backtester(SETTINGS.initial_equity, costs).run(bars, strategy)
    return result.summary()


print("=" * 80)
print("PASADA 4 · SWEEP bear_cap + SIZING ADAPTATIVO · 2017-2026 completo")
print("=" * 80)

BASE = {"volume_window": 20, "holding": 3, "return_threshold": -0.025,
        "volume_multiple": 1.5, "fit_window": 120, "refit_every": 20,
        "target_vol": 0.02, "hard_block": 0.70}

configs = []
for cap in [0.50, 0.55, 0.60, 0.65]:
    configs.append((f"gate bear>{cap:.2f}", {**BASE, "bear_posterior_cap": cap, "mode": "gate"}))
    configs.append((f"size bear>{cap:.2f}", {**BASE, "bear_posterior_cap": cap, "mode": "sizing"}))

results = []
for label, params in configs:
    s_full = run(label, bars_all, params)
    s_26 = run(label, bars_2026, params)
    r = {"label": label, "params": params,
         "full": s_full, "fwd2026": s_26}
    results.append(r)
    print(f"\n--- {label} ---", flush=True)
    print(f"  FULL  ret {s_full['net_return']:+7.2%} | DD {s_full['drawdown']:5.2%} | "
          f"PF {s_full['profit_factor']:.2f} | Sh {s_full['sharpe']:.2f} | "
          f"T {s_full.get('trades','?')}", flush=True)
    print(f"  2026  ret {s_26['net_return']:+7.2%} | DD {s_26['drawdown']:5.2%} | "
          f"PF {s_26['profit_factor']:.2f} | T {s_26.get('trades','?')}", flush=True)

# Mejor por 2026
pos26 = [r for r in results if r["fwd2026"]["net_return"] > 0]
print(f"\n=== RANKING FORWARD 2026 ===")
print(f"Positivos en 2026: {len(pos26)}/{len(results)}")
for r in sorted(results, key=lambda x: x["fwd2026"]["net_return"], reverse=True)[:5]:
    f, s26 = r["full"], r["fwd2026"]
    print(f"  {r['label']:20s} | 2026: {s26['net_return']:+6.2%} DD {s26['drawdown']:5.2%} "
          f"T {s26.get('trades','?')} | FULL: {f['net_return']:+7.2%} DD {f['drawdown']:5.2%}")

out = Path("research/iterations/forward_sweep")
out.mkdir(parents=True, exist_ok=True)
(out / "results.json").write_text(json.dumps(results, indent=1, default=str))
print(f"\n[ok] guardado en {out}/results.json")
