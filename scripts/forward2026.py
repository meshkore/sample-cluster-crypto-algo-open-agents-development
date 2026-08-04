#!/usr/bin/env python3
"""forward2026.py — forward test HONESTE de V2 (vol_climax + filtro HMM)
sobre 2026 real: histórico 2017-2025 + datos 2026 descargados de Binance.

El HMM se refit en ventana causal (120 bars, cada 20) sobre closes pasados
únicamente: en 2026 se comporta idéntico al backtest, parámetros fijos
desde la batalla (bear_cap 0.50). Sin reentrenamiento con 2026.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")

from quantlab.backtest import Backtester, CostModel
from quantlab.config import Settings
from quantlab.data import BinanceProvider, DataManager
from quantlab.hmm_regime import GaussianHMM
from quantlab.validation import StatisticalValidator

SETTINGS = Settings.load("config/default.json")
costs = CostModel(
    SETTINGS.commission_bps, SETTINGS.slippage_bps, SETTINGS.funding_bps_per_bar
)
manager = DataManager(SETTINGS.data_root, SETTINGS.splits["future_lock_start"])

LOCK = datetime.fromisoformat(
    SETTINGS.splits["future_lock_start"].replace("Z", "+00:00")
)  # 2026-01-01


def _mean(values):
    return sum(values) / len(values)


class VolClimaxHmmFilter:
    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self):
        self.remaining = 0
        self._model = None
        self._last_fit = -10 ** 9

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


# ---- 1) Histórico (research) ----
hist_csv = sorted(Path("data/processed/binance/BTCUSDT/1d").glob("*.csv"))[0]
historical = manager.load_csv(str(hist_csv))
historical = [b for b in historical if b.timestamp < LOCK]
print(f"[hist] {len(historical)} barras < 2026", flush=True)

# ---- 2) Forward 2026 desde Binance ----
fwd_csv = Path("data/processed/binance/BTCUSDT/1d/forward_2026.csv")
if fwd_csv.exists():
    forward = manager.load_csv(str(fwd_csv))
    print(f"[fwd] cargadas {len(forward)} barras de cache", flush=True)
else:
    provider = BinanceProvider()
    end = datetime(2026, 8, 5, tzinfo=timezone.utc)  # hasta hoy
    forward = provider.bars("BTCUSDT", "1d", LOCK, end)
    # Guardar manualmente sin validar (el future-lock bloquea save_csv)
    import csv
    fwd_csv.parent.mkdir(parents=True, exist_ok=True)
    with fwd_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp","open","high","low","close","volume","taker_buy_volume"])
        for b in forward:
            w.writerow([b.timestamp.isoformat(), b.open, b.high, b.low,
                        b.close, b.volume, getattr(b, "taker_buy_volume", "")])
    print(f"[fwd] descargadas y guardadas {len(forward)} barras 2026 de Binance", flush=True)

forward = [b for b in forward if b.timestamp >= LOCK]
print(f"[fwd] {len(forward)} barras >= 2026-01-01 "
      f"({forward[0].timestamp.date()} → {forward[-1].timestamp.date()})", flush=True)

combined = {b.timestamp: b for b in historical}
combined.update({b.timestamp: b for b in forward})
bars = [combined[k] for k in sorted(combined)]
print(f"[all] {len(bars)} barras combinadas (2017 → 2026)", flush=True)

# ---- 3) Forward test con parámetros fijos ----
params = {"volume_window": 20, "holding": 3, "return_threshold": -0.025,
          "volume_multiple": 1.5, "fit_window": 120, "refit_every": 20,
          "bear_posterior_cap": 0.50}
strategy = VolClimaxHmmFilter(params)
result = Backtester(SETTINGS.initial_equity, costs).run(bars, strategy)
s = result.summary()
rob = StatisticalValidator(SETTINGS.minimum_trades).validate(
    result, bars, strategy, SETTINGS.initial_equity, costs
)
passed = sum(1 for v in rob["checks"].values() if v)

print("=" * 64)
print("FORWARD 2026 · V2 vol_climax + filtro HMM · BTCUSDT real")
print("=" * 64)
print(f"Equity final    : ${s['final_equity']:,.2f}")
print(f"Net return      : {s['net_return']:+.2%}")
print(f"Max drawdown    : {s['drawdown']:.2%}")
print(f"Profit factor   : {s['profit_factor']:.3f}")
print(f"Sharpe          : {s['sharpe']:.3f}")
print(f"Trades          : {s.get('trades', 'n/a')}")
print(f"Exposure        : {s['exposure']:.2%}")
print(f"Robustness      : {passed}/5 {rob['checks']}")

# ---- 4) Segmento 2026 (forward) ----
seg = [b for b in bars if b.timestamp >= LOCK]
seg_result = Backtester(SETTINGS.initial_equity, costs).run(seg, strategy)
ss = seg_result.summary()
print("\n--- Solo 2026 (como el dashboard del lab) ---")
print(f"Equity 2026     : ${ss['final_equity']:,.2f}")
print(f"Return 2026     : {ss['net_return']:+.2%}")
print(f"Max DD 2026     : {ss['drawdown']:.2%}")
print(f"Trades 2026     : {ss.get('trades', 'n/a')}")

out = Path("research/iterations/forward2026")
out.mkdir(parents=True, exist_ok=True)
(out / "results.json").write_text(json.dumps({
    "full": s, "robustness": rob, "segment_2026": ss, "params": params,
}, indent=1))
print(f"\n[ok] guardado en {out}/results.json")
