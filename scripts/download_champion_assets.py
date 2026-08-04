#!/usr/bin/env python3
"""download_champion_assets.py — descarga los assets que tradea el champion
S00743 (BTC, BNB, ADA, TRX, WBTC, PAXG) + top líquidos, 2017-2025.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")

from quantlab.config import Settings
from quantlab.data import BinanceProvider, DataManager

SETTINGS = Settings.load("config/default.json")
manager = DataManager(SETTINGS.data_root, SETTINGS.splits["future_lock_start"])
provider = BinanceProvider()

ASSETS = ["BTCUSDT", "BNBUSDT", "ADAUSDT", "TRXUSDT", "WBTCUSDT", "PAXGUSDT",
          "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT"]
start = datetime(2017, 8, 17, tzinfo=timezone.utc)
end = datetime(2025, 12, 31, tzinfo=timezone.utc)

for symbol in ASSETS:
    try:
        bars = provider.bars(symbol, "1d", start, end)
        manager.validate(bars)
        path = manager.save_csv(bars, "binance", symbol, "1d")
        print(f"[ok] {symbol}: {len(bars)} barras → {path.name[:16]}", flush=True)
    except Exception as e:
        print(f"[err] {symbol}: {e}", flush=True)
print("[done]")
