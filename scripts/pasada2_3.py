#!/usr/bin/env python3
"""pasada2_3.py — pasada 2 (micro-sweep bear_cap) + pasada 3 (multi-asset)
con la clase ORIGINAL de la batalla (posterior HMM por barra, la que dio
+53.5% / DD 14.8%). El "fast" degradaba el filtro (solo refit), por eso
se descarta.

Pasada 2: bear_cap en {0.40, 0.45, 0.50, 0.55} en BTCUSDT.
Pasada 3: mejor bear_cap validado en los 12 assets reales.
"""
import json
import sys
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


def _mean(values):
    return sum(values) / len(values)


class VolClimaxHmmFilter:
    """Original de la batalla: posterior HMM en CADA barra (ventana causal)."""

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


BASE = {"volume_window": 20, "holding": 3, "return_threshold": -0.025,
        "volume_multiple": 1.5, "fit_window": 120, "refit_every": 20,
        "bear_posterior_cap": 0.50}


def load(symbol):
    csv = sorted(Path(f"data/processed/binance/{symbol}/1d").glob("*.csv"))[0]
    return manager.load_csv(str(csv))


def run(bars, params):
    strategy = VolClimaxHmmFilter(params)
    result = Backtester(SETTINGS.initial_equity, costs).run(bars, strategy)
    s = result.summary()
    rob = StatisticalValidator(SETTINGS.minimum_trades).validate(
        result, bars, strategy, SETTINGS.initial_equity, costs
    )
    passed = sum(1 for v in rob["checks"].values() if v)
    return {
        "net": s["net_return"], "dd": s["drawdown"], "pf": s["profit_factor"],
        "sharpe": s["sharpe"], "trades": s.get("trades", "n/a"),
        "exposure": s["exposure"], "robust": passed,
        "double_cost": rob.get("double_cost_net_return"),
    }


print("=" * 70)
print("PASADA 2 · micro-sweep bear_cap (BTCUSDT real, posterior por barra)")
print("=" * 70)
btc = load("BTCUSDT")
sweep_rows = []
for cap in [0.40, 0.45, 0.50, 0.55, 0.60]:
    p = {**BASE, "bear_posterior_cap": cap}
    r = run(btc, p)
    sweep_rows.append({"cap": cap, **r})
    tag = " ✅" if r["robust"] >= 4 and r["net"] > 0 else ""
    print(f"bear>{cap:.2f} → ret {r['net']:+7.2%} | DD {r['dd']:5.2%} | "
          f"PF {r['pf']:.2f} | Sh {r['sharpe']:.2f} | T {r['trades']} | "
          f"rob {r['robust']}/5{tag}", flush=True)

good = [r for r in sweep_rows if r["robust"] >= 4 and r["net"] > 0]
best_cap = max(good, key=lambda r: r["net"] - r["dd"] * 2)["cap"] if good else 0.50
print(f"\n→ mejor bear_cap: {best_cap:.2f}")

print()
print("=" * 70)
print(f"PASADA 3 · V2 (bear>{best_cap:.2f}) en 12 assets reales 2017-2025")
print("=" * 70)
ASSETS = ["BTCUSDT", "BNBUSDT", "ADAUSDT", "TRXUSDT", "WBTCUSDT", "PAXGUSDT",
          "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT"]
rows = []
for symbol in ASSETS:
    try:
        bars = load(symbol)
    except Exception as e:
        print(f"[{symbol}] error: {e}", flush=True)
        continue
    r = run(bars, {**BASE, "bear_posterior_cap": best_cap})
    rows.append({"symbol": symbol, "bars": len(bars), **r})
    print(f"[{symbol:9s}] {len(bars):5d} → ret {r['net']:+7.2%} | DD {r['dd']:5.2%} | "
          f"PF {r['pf']:.2f} | Sh {r['sharpe']:.2f} | T {r['trades']} | rob {r['robust']}/5",
          flush=True)

wins = [r for r in rows if r["net"] > 0]
rob4 = [r for r in rows if r["robust"] >= 4]
avg = sum(r["net"] for r in rows) / len(rows) if rows else 0
print("\n=== RESUMEN MULTI-ASSET ===")
print(f"Assets {len(rows)} | positivos {len(wins)} | robustos 4/5+ {len(rob4)} | ret medio {avg:+.2%}")
for r in sorted(rows, key=lambda x: x["net"], reverse=True)[:5]:
    print(f"  {r['symbol']:9s} {r['net']:+7.2%} DD {r['dd']:5.2%} rob {r['robust']}/5")

out = Path("research/iterations/pasada2_3")
out.mkdir(parents=True, exist_ok=True)
(out / "results.json").write_text(json.dumps({
    "best_bear_cap": best_cap, "sweep": sweep_rows, "assets": rows,
    "avg_net": avg, "wins": len(wins), "robust4": len(rob4),
}, indent=1))
print(f"[ok] guardado en {out}/results.json")
