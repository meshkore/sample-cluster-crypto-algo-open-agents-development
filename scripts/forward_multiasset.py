#!/usr/bin/env python3
"""forward_multiasset.py — forward 2026 MULTI-ASSET de V2.

Descarga 2026 para los 12 assets, corre V2 (gate + sizing) en cada uno,
y calcula el portfolio equal-weight (como el benchmark del lab).
"""
import json, sys, math, csv
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")

from quantlab.backtest import Backtester, CostModel
from quantlab.config import Settings
from quantlab.data import BinanceProvider, DataManager
from quantlab.hmm_regime import GaussianHMM

SETTINGS = Settings.load("config/default.json")
costs = CostModel(SETTINGS.commission_bps, SETTINGS.slippage_bps, SETTINGS.funding_bps_per_bar)
manager = DataManager(SETTINGS.data_root, SETTINGS.splits["future_lock_start"])
LOCK = datetime.fromisoformat(SETTINGS.splits["future_lock_start"].replace("Z", "+00:00"))
provider = BinanceProvider()

ASSETS = ["BTCUSDT", "BNBUSDT", "ADAUSDT", "TRXUSDT", "ETHUSDT", "SOLUSDT",
          "XRPUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT", "PAXGUSDT", "WBTCUSDT"]


def _mean(v): return sum(v) / len(v)


class VolClimaxHmmSizing:
    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self):
        self.remaining = 0
        self._model = None
        self._last_fit = -10**9
        self._state_vols = [0.02, 0.02, 0.02]

    def on_bar(self, bars):
        window = int(self.params.get("volume_window", 20))
        holding = int(self.params.get("holding", 3))
        fit_window = int(self.params.get("fit_window", 120))
        refit_every = int(self.params.get("refit_every", 20))
        bear_cap = float(self.params.get("bear_posterior_cap", 0.50))
        hard_block = float(self.params.get("hard_block", 0.70))
        mode = self.params.get("mode", "sizing")
        target_vol = float(self.params.get("target_vol", 0.02))
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
            self.params.get("volume_multiple", 1.5)):
            self.remaining = holding
        if self.remaining <= 0:
            return 0.0
        self.remaining = max(0, self.remaining - 1)
        if mode == "gate":
            if bear >= bear_cap:
                self.remaining = 0
                return 0.0
            return 1.0
        else:
            dom_state = max(range(3), key=lambda s: p[s])
            sv = self._state_vols[dom_state]
            bear_penalty = max(0.0, 1.0 - bear * 1.5)
            raw = target_vol / sv if sv > 1e-8 else 1.0
            size = max(0.15, min(1.0, raw)) * bear_penalty
            if bear >= bear_cap:
                size *= 0.5
            return size


def load_or_download(symbol):
    """Carga histórico + descarga 2026 si no existe, combina."""
    hist_csvs = sorted(Path(f"data/processed/binance/{symbol}/1d").glob("*.csv"))
    hist_csv = hist_csvs[0] if hist_csvs else None
    fwd_csv = Path(f"data/processed/binance/{symbol}/1d/forward_2026.csv")

    historical = manager.load_csv(str(hist_csv)) if hist_csv else []
    historical = [b for b in historical if b.timestamp < LOCK]

    if not fwd_csv.exists():
        try:
            fwd_bars = provider.bars(symbol, "1d", LOCK, datetime(2026, 8, 5, tzinfo=timezone.utc))
            fwd_csv.parent.mkdir(parents=True, exist_ok=True)
            with fwd_csv.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["timestamp","open","high","low","close","volume","taker_buy_volume"])
                for b in fwd_bars:
                    w.writerow([b.timestamp.isoformat(), b.open, b.high, b.low,
                                b.close, b.volume, getattr(b, "taker_buy_volume", "")])
            print(f"  [{symbol}] 2026 descargado: {len(fwd_bars)} barras", flush=True)
        except Exception as e:
            print(f"  [{symbol}] error descarga 2026: {e}", flush=True)
            return historical, []

    forward = manager.load_csv(str(fwd_csv)) if fwd_csv.exists() else []
    forward = [b for b in forward if b.timestamp >= LOCK]
    return historical, forward


# --- Forward multi-asset ---
print("=" * 80)
print("FORWARD 2026 MULTI-ASSET · V2 sizing adaptativo")
print("=" * 80)

PARAMS_SIZING = {"volume_window": 20, "holding": 3, "return_threshold": -0.025,
                 "volume_multiple": 1.5, "fit_window": 120, "refit_every": 20,
                 "bear_posterior_cap": 0.50, "hard_block": 0.70,
                 "mode": "sizing", "target_vol": 0.02}

PARAMS_GATE = {**PARAMS_SIZING, "mode": "gate"}

rows = []
for symbol in ASSETS:
    print(f"\n[{symbol}]", flush=True)
    hist, fwd = load_or_download(symbol)
    if not fwd:
        print(f"  sin datos 2026, skip", flush=True)
        continue
    combined = {b.timestamp: b for b in hist}
    combined.update({b.timestamp: b for b in fwd})
    bars_full = [combined[k] for k in sorted(combined)]
    bars_2026 = [b for b in bars_full if b.timestamp >= LOCK]

    for mode_label, params in [("sizing", PARAMS_SIZING), ("gate", PARAMS_GATE)]:
        s_full = Backtester(SETTINGS.initial_equity, costs).run(bars_full, VolClimaxHmmSizing(params)).summary()
        s_26 = Backtester(SETTINGS.initial_equity, costs).run(bars_2026, VolClimaxHmmSizing(params)).summary()
        rows.append({"symbol": symbol, "mode": mode_label,
                     "full_ret": s_full["net_return"], "full_dd": s_full["drawdown"],
                     "full_trades": s_full.get("trades", 0),
                     "fwd_ret": s_26["net_return"], "fwd_dd": s_26["drawdown"],
                     "fwd_trades": s_26.get("trades", 0)})
        print(f"  {mode_label:6s} FULL {s_full['net_return']:+7.2%} DD {s_full['drawdown']:5.2%} T{s_full.get('trades',0):3d}"
              f" | 2026 {s_26['net_return']:+7.2%} DD {s_26['drawdown']:5.2%} T{s_26.get('trades',0):3d}",
              flush=True)

# Portfolio equal-weight (como el benchmark del lab)
print("\n\n=== PORTFOLIO EQUAL-WEIGHT (promedio de assets) ===")
for mode in ["sizing", "gate"]:
    subset = [r for r in rows if r["mode"] == mode]
    avg_fwd = sum(r["fwd_ret"] for r in subset) / len(subset) if subset else 0
    avg_full = sum(r["full_ret"] for r in subset) / len(subset) if subset else 0
    total_trades = sum(r["fwd_trades"] for r in subset)
    wins = [r for r in subset if r["fwd_ret"] > 0]
    print(f"  {mode:6s} | 2026 avg {avg_fwd:+.2%} | {len(wins)}/{len(subset)} positivos"
          f" | {total_trades} trades totales | FULL avg {avg_full:+.2%}")

print("\n=== TOP 5 ASSETS EN FORWARD 2026 ===")
for r in sorted(rows, key=lambda x: x["fwd_ret"], reverse=True)[:5]:
    print(f"  {r['symbol']:9s} {r['mode']:6s} | 2026 {r['fwd_ret']:+7.2%} DD {r['fwd_dd']:5.2%} "
          f"T{r['fwd_trades']:3d} | FULL {r['full_ret']:+7.2%}")

out = Path("research/iterations/forward_multiasset")
out.mkdir(parents=True, exist_ok=True)
(out / "results.json").write_text(json.dumps(rows, indent=1))
print(f"\n[ok] guardado")
