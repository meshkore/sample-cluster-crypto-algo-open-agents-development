#!/usr/bin/env python3
"""multiasset_validate.py — pasada 3: valida la mejor V2 (filtro HMM)
sobre los 12 assets reales descargados, con igualdad de pesos tipo
equal-weight benchmark del lab. Lee el mejor params de sweep_filter/results.json
si existe, si no usa el ganador conocido (bear 0.50, refit 20, fit 120).
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

ASSETS = ["BTCUSDT", "BNBUSDT", "ADAUSDT", "TRXUSDT", "WBTCUSDT", "PAXGUSDT",
          "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT"]


def _mean(values):
    return sum(values) / len(values)


class VolClimaxHmmFilterFast:
    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self):
        self.remaining = 0
        self._model = None
        self._last_fit = -10 ** 9
        self._bear = 0.0

    def on_bar(self, bars):
        window = int(self.params.get("volume_window", 20))
        holding = int(self.params.get("holding", 3))
        fit_window = int(self.params.get("fit_window", 120))
        refit_every = int(self.params.get("refit_every", 20))
        bear_cap = float(self.params.get("bear_posterior_cap", 0.5))
        i = len(bars) - 1
        if i < max(window, fit_window):
            return 0.0
        if i - self._last_fit >= refit_every:
            closes = [b.close for b in bars[i - fit_window + 1 : i + 1]]
            model = GaussianHMM(n_states=3, seed=42).fit(closes)
            self._model = model.sorted_by_mean()
            self._last_fit = i
            post = self._model.posterior(closes)
            self._bear = post[-1][0]
        if self._bear >= bear_cap:
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


# Mejor params del sweep si existe
BEST = {"volume_window": 20, "holding": 3, "return_threshold": -0.025,
        "volume_multiple": 1.5, "fit_window": 120, "refit_every": 20,
        "bear_posterior_cap": 0.50}
sweep_file = Path("research/iterations/sweep_filter/results.json")
if sweep_file.exists():
    try:
        results = json.loads(sweep_file.read_text())
        good = [r for r in results if r["robust"] >= 4 and r["net"] > 0]
        if good:
            good.sort(key=lambda r: r["net"] - r["dd"] * 2, reverse=True)
            BEST = good[0]["params"]
            print(f"[best] del sweep: bear>{BEST['bear_posterior_cap']:.2f} "
                  f"refit={BEST['refit_every']} fit={BEST['fit_window']} "
                  f"(ret {good[0]['net']:+.2%}, DD {good[0]['dd']:.2%})", flush=True)
    except Exception:
        pass

print("=" * 70)
print("PASADA 3 · V2 filtro HMM en 12 assets reales (2017-2025)")
print(f"params: bear>{BEST['bear_posterior_cap']:.2f} refit={BEST['refit_every']} "
      f"fit={BEST['fit_window']} hold={BEST['holding']}")
print("=" * 70)

summary_rows = []
for symbol in ASSETS:
    try:
        csv = sorted(Path(f"data/processed/binance/{symbol}/1d").glob("*.csv"))[0]
        bars = manager.load_csv(str(csv))
    except Exception as e:
        print(f"[{symbol}] error carga: {e}", flush=True)
        continue
    strategy = VolClimaxHmmFilterFast(BEST)
    result = Backtester(SETTINGS.initial_equity, costs).run(bars, strategy)
    s = result.summary()
    rob = StatisticalValidator(SETTINGS.minimum_trades).validate(
        result, bars, strategy, SETTINGS.initial_equity, costs
    )
    passed = sum(1 for v in rob["checks"].values() if v)
    summary_rows.append({
        "symbol": symbol, "bars": len(bars), "net": s["net_return"],
        "dd": s["drawdown"], "pf": s["profit_factor"], "sharpe": s["sharpe"],
        "trades": s.get("trades", "n/a"), "robust": passed,
    })
    print(f"[{symbol:9s}] {len(bars):5d} barras → ret {s['net_return']:+7.2%} | "
          f"DD {s['drawdown']:5.2%} | PF {s['profit_factor']:.2f} | "
          f"Sh {s['sharpe']:.2f} | T {s.get('trades','n/a')} | rob {passed}/5",
          flush=True)

if summary_rows:
    wins = [r for r in summary_rows if r["net"] > 0]
    rob4 = [r for r in summary_rows if r["robust"] >= 4]
    avg_net = sum(r["net"] for r in summary_rows) / len(summary_rows)
    print("\n=== RESUMEN MULTI-ASSET ===")
    print(f"Assets: {len(summary_rows)} | positivos: {len(wins)} | robustos 4/5+: {len(rob4)}")
    print(f"Retorno medio: {avg_net:+.2%}")
    for r in sorted(summary_rows, key=lambda x: x["net"], reverse=True)[:5]:
        print(f"  {r['symbol']:9s} {r['net']:+7.2%} DD {r['dd']:5.2%} rob {r['robust']}/5")

out = Path("research/iterations/multiasset")
out.mkdir(parents=True, exist_ok=True)
(out / "results.json").write_text(json.dumps({
    "params": BEST, "assets": summary_rows,
    "avg_net": avg_net, "wins": len(wins), "robust4": len(rob4),
}, indent=1))
print(f"[ok] guardado en {out}/results.json")
