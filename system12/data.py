"""Market data: Binance spot klines (4h, 1d) and USD-M perpetual funding, cached as CSV in config.CANDLES_DIR.

A cache younger than one hour is used as is; otherwise only the missing tail is downloaded. Bars are stamped at
their close (open time + bar length) and only closed bars are kept.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

from .config import BAR_NS, CANDLES_DIR

SPOT = "https://api.binance.com/api/v3/klines"
FUNDING = "https://fapi.binance.com/fapi/v1/fundingRate"
HISTORY_START = pd.Timestamp("2017-09-01")
FUNDING_START = pd.Timestamp("2019-09-01")
MAX_AGE_S = 3600


def _get(url: str):
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "system12/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except OSError:
            if attempt == 4:
                raise
            time.sleep(2 * (attempt + 1))


def _cached(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path, index_col=0) if path.exists() else None


def _fresh(path: Path) -> bool:
    return path.exists() and time.time() - path.stat().st_mtime < MAX_AGE_S


def _ms(ts: pd.Timestamp) -> int:
    return int(ts.timestamp() * 1000)


def _save(df: pd.DataFrame, path: Path, index_name: str) -> pd.DataFrame:
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.index.name = index_name
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)
    return df


def klines(coin: str, tf: str) -> pd.DataFrame:
    """Close-stamped spot bars indexed by close time (ns): open, high, low, close, usd (quote volume)."""
    path = CANDLES_DIR / f"{coin}USDT_{tf}.csv"
    old = _cached(path)
    if old is not None and _fresh(path):
        return old
    step_ms = BAR_NS[tf] // 10**6
    t0 = int(old.index[-1]) // 10**6 - step_ms if old is not None and len(old) else _ms(HISTORY_START)
    now_ms = int(time.time() * 1000)
    rows = []
    while t0 < now_ms:
        batch = _get(f"{SPOT}?symbol={coin}USDT&interval={tf}&startTime={t0}&limit=1000")
        if not batch:
            break
        rows += [(int(k[0]) + step_ms, *map(float, (k[1], k[2], k[3], k[4], k[7]))) for k in batch]
        t0 = int(batch[-1][0]) + step_ms
        time.sleep(0.1)
    new = pd.DataFrame(rows, columns=["close_ms", "open", "high", "low", "close", "usd"])
    new = new[new["close_ms"] <= now_ms]  # closed bars only
    new.index = new.pop("close_ms").astype("int64") * 10**6
    return _save(pd.concat([old, new]) if old is not None else new, path, "close_ns")


def funding(coin: str) -> pd.Series:
    """Perpetual funding settlements indexed by settlement time (ns)."""
    path = CANDLES_DIR / f"{coin}USDT_funding.csv"
    old = _cached(path)
    if old is not None and _fresh(path):
        return old["rate"]
    t0 = int(old.index[-1]) // 10**6 + 1 if old is not None and len(old) else _ms(FUNDING_START)
    rows = []
    while True:
        batch = _get(f"{FUNDING}?symbol={coin}USDT&startTime={t0}&limit=1000")
        rows += [(int(r["fundingTime"]) * 10**6, float(r["fundingRate"])) for r in batch]
        if len(batch) < 1000:
            break
        t0 = int(batch[-1]["fundingTime"]) + 1
        time.sleep(0.2)
    new = pd.DataFrame(rows, columns=["t_ns", "rate"]).set_index("t_ns")
    return _save(pd.concat([old, new]) if old is not None else new, path, "t_ns")["rate"]
