"""Point-in-time universe (audit 2026-10-15, item 1): no coin is chosen with knowledge of 2026.

For test year N the eligible coins are the USDT pairs that, on 31 December of N-1 (every bar
strictly before 1 January N 00:00 UTC), had

    * >= 540 days of 15m history (first candle on disk to the cut), and
    * a trailing-30-day turnover >= the floor system 06's universe uses (USD 10M a day),
      measured on the candles on disk as sum(close x volume) / 30,

delisted pairs included while they qualify (their candles come from Binance's archive,
`research/system10/tools/pit_data.py`). Ranked by that turnover; `cap` keeps the top k.
Same stablecoin exclusion as 06's universe. Nothing after the cut is read.

    python -m system010_conditioned_rl.universe_pit     # writes research/system10/rnd/universe_pit.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from quantlab_catalog.paths import DATA_ROOT
from system006_oracle_net_15m.universe import DEFAULT_MIN_HISTORY_DAYS, DEFAULT_MIN_TURNOVER, STABLE_BASES

REPO = Path(__file__).resolve().parents[3]
ARTEFACT = REPO / "research/system10/rnd/universe_pit.json"
YEARS = tuple(range(2020, 2027))
DAY_NS = 86_400 * 10**9
WINDOW_DAYS = 30
COMPLETE_TO_RANK = 30   # pit_data.py fetched the archive screen's top 30 per year


def cut_ns(year: int) -> int:
    """1 January `year` 00:00 UTC: the first instant that may NOT be read for year's list."""
    return int(np.datetime64(f"{year}-01-01T00:00:00", "ns").astype(np.int64))


def stats_at(ns: np.ndarray, close: np.ndarray, volume: np.ndarray, year: int) -> dict:
    """Age (days) and trailing-30-day mean daily turnover at the cut of `year`, from bars
    strictly before it."""
    cut = cut_ns(year)
    before = ns < cut
    if not before.any():
        return {"age_days": 0.0, "turnover30": 0.0}
    age = (cut - int(ns[before][0])) / DAY_NS
    win = before & (ns >= cut - WINDOW_DAYS * DAY_NS)
    turn = float(np.sum(close[win] * volume[win])) / WINDOW_DAYS
    return {"age_days": round(age, 2), "turnover30": round(turn, 0)}


def eligible(stats: dict[str, dict], year: int, floor: float = DEFAULT_MIN_TURNOVER,
             min_days: float = DEFAULT_MIN_HISTORY_DAYS, cap: int | None = None) -> list[str]:
    """`stats[symbol][year]` -> the year's eligible symbols, highest turnover first."""
    rows = [(s, st[year]) for s, st in stats.items() if year in st]
    ok = [(s, v) for s, v in rows if v["age_days"] >= min_days and v["turnover30"] >= floor]
    ok.sort(key=lambda x: -x[1]["turnover30"])
    out = [s for s, _ in ok]
    return out[:cap] if cap else out


def _base(symbol: str) -> str:
    return symbol.split("_")[0][:-4]


def on_disk() -> list[str]:
    """Every USDT pair with research 15m candles in the catalogue (stablecoins excluded)."""
    root = DATA_ROOT / "research" / "processed" / "binance"
    out = []
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        if (d.name.split("_")[0].endswith("USDT") and _base(d.name) not in STABLE_BASES
                and any((d / "15m").glob("*.csv"))):
            out.append(d.name)
    return out


def read_candles(symbol: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(ns, close, volume) of the catalogue's research file for `symbol` (the one the loader
    would pick: the furthest observed end)."""
    import pandas as pd
    from quantlab_backtester.data import _cached_dataset
    path = _cached_dataset(DATA_ROOT / "research" / "processed" / "binance" / symbol / "15m", None)
    df = pd.read_csv(path, usecols=["timestamp", "close", "volume"])
    ts = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    ns = ts.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    return ns, df["close"].to_numpy(float), df["volume"].to_numpy(float)


def build(symbols: list[str] | None = None, years=YEARS) -> dict:
    stats: dict[str, dict] = {}
    for s in symbols or on_disk():
        ns, close, vol = read_candles(s)
        stats[s] = {y: stats_at(ns, close, vol, y) for y in years}
    doc = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "rule": (f">= {DEFAULT_MIN_HISTORY_DAYS} days of 15m history and trailing-{WINDOW_DAYS}-day "
                    f"turnover >= {DEFAULT_MIN_TURNOVER:,.0f} USD/day on 31 Dec of N-1; delisted included"),
           "floor": DEFAULT_MIN_TURNOVER, "min_days": DEFAULT_MIN_HISTORY_DAYS,
           "pairs_on_disk": len(stats),
           "complete_to_rank": COMPLETE_TO_RANK,
           "note": ("candles were fetched for the top 30 per year of the archive screen (pit_data.py), "
                    "so each list is complete to that rank; pairs below it may be missing"),
           "years": {}}
    for y in years:
        el = eligible(stats, y)
        doc["years"][str(y)] = [{"symbol": s, "turnover30_musd": round(stats[s][y]["turnover30"] / 1e6, 1),
                                 "age_days": int(stats[s][y]["age_days"])} for s in el]
    return doc


def load(year: int, cap: int | None = None, path: Path = ARTEFACT) -> list[str]:
    """The frozen eligible list of `year` from the artefact, highest turnover first."""
    rows = json.loads(Path(path).read_text())["years"][str(year)]
    out = [r["symbol"] for r in rows]
    return out[:cap] if cap else out


def main() -> int:
    doc = build()
    ARTEFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTEFACT.write_text(json.dumps(doc, indent=1))
    for y, rows in doc["years"].items():
        print(y, len(rows), " ".join(r["symbol"] for r in rows))
    print(f"-> {ARTEFACT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
