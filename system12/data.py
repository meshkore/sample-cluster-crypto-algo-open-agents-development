"""Market data for System 12: Binance spot klines (4h and 1d) for BTC and ETH, and USD-M perpetual funding.

Everything is cached outside the repository, in DATA_DIR (env QUANTLAB_DATA, default ../meshkore-crypto-data/system12
next to the repo). A cache is refreshed when it is older than one hour; only the missing tail is downloaded.

Bars are stamped at their CLOSE (open time + bar length) and only closed bars are kept.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("QUANTLAB_DATA", ROOT.parent / "meshkore-crypto-data" / "system12"))
COINS = ("BTC", "ETH")
START = "2017-09-01"
STEP = {"4h": 4 * 3600 * 10**9, "1d": 24 * 3600 * 10**9}
UA = {"User-Agent": "system12/1.0"}
FRESH_S = 3600


def _get(url: str):
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001 - network hiccup: retry with backoff
            if k == 4:
                raise
            time.sleep(2 * (k + 1))


def _fresh(f: Path) -> bool:
    return f.exists() and time.time() - f.stat().st_mtime < FRESH_S


def klines(coin: str, tf: str) -> pd.DataFrame:
    """Close-stamped spot bars: index = close time (ns), columns open, high, low, close, usd (quote volume)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    f = DATA_DIR / f"{coin}USDT_{tf}.csv"
    old = pd.read_csv(f, index_col=0) if f.exists() else None
    if old is not None and _fresh(f):
        return old
    step_ms = STEP[tf] // 10**6
    t0 = int(old.index[-1]) // 10**6 - step_ms if old is not None and len(old) else int(pd.Timestamp(START).timestamp() * 1000)
    now_ms = int(time.time() * 1000)
    rows = []
    while t0 < now_ms:
        d = _get(f"https://api.binance.com/api/v3/klines?symbol={coin}USDT&interval={tf}&startTime={t0}&limit=1000")
        if not d:
            break
        rows += [(int(k[0]) + step_ms, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7])) for k in d]
        t0 = int(d[-1][0]) + step_ms
        time.sleep(0.1)
    new = pd.DataFrame(rows, columns=["close_ms", "open", "high", "low", "close", "usd"])
    new = new[new["close_ms"] <= now_ms]  # closed bars only
    new.index = new.pop("close_ms").astype(np.int64) * 10**6
    df = pd.concat([old, new]) if old is not None else new
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.index.name = "close_ns"
    df.to_csv(f)
    return df


def funding(coin: str) -> pd.Series:
    """Perpetual funding settlements: index = settlement time (ns), value = rate."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    f = DATA_DIR / f"{coin}USDT_funding.csv"
    old = pd.read_csv(f, index_col=0)["rate"] if f.exists() else None
    if old is not None and _fresh(f):
        return old
    t0 = int(old.index[-1]) // 10**6 + 1 if old is not None and len(old) else int(pd.Timestamp("2019-09-01").timestamp() * 1000)
    rows = []
    while True:
        d = _get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={coin}USDT&startTime={t0}&limit=1000")
        if not d:
            break
        rows += [(int(r["fundingTime"]) * 10**6, float(r["fundingRate"])) for r in d]
        if len(d) < 1000:
            break
        t0 = int(d[-1]["fundingTime"]) + 1
        time.sleep(0.2)
    new = pd.Series({t: v for t, v in rows}, dtype=float)
    s = pd.concat([old, new]) if old is not None else new
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s.index.name = "t_ns"
    s.rename("rate").to_frame().to_csv(f)
    return s
