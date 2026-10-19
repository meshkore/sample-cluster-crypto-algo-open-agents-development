"""Download Binance USD-M perpetual funding history for every PIT coin (public endpoint, no key).

Writes research/plan_v2/cache/funding_<SYMBOL>.json as [{"t_ms", "rate"}]. A coin with no rows had no
USD-M perpetual: it can be held long (spot) but never shorted. Delisted perps keep their history.

    python research/plan_v2/fetch_funding.py
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
URL = "https://fapi.binance.com/fapi/v1/fundingRate?symbol={s}&startTime={t}&limit=1000"
START = 1_546_300_800_000      # 2019-01-01
END = 1_767_225_600_000        # 2026-01-01 (research bars only)


def fetch(sym: str) -> list[dict]:
    rows, t = [], START
    while t < END:
        try:
            with urllib.request.urlopen(URL.format(s=sym, t=t), timeout=30) as r:
                batch = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 400:       # unknown symbol: never had a USD-M perpetual
                return []
            raise
        if not batch:
            break
        rows += [{"t_ms": int(b["fundingTime"]), "rate": float(b["fundingRate"])} for b in batch
                 if int(b["fundingTime"]) < END]
        t = int(batch[-1]["fundingTime"]) + 1
        if len(batch) < 1000:
            break
        time.sleep(0.25)
    return rows


def main() -> int:
    from system010_conditioned_rl import pit
    lists = pit.union_lists(pit.CAP, pit.UNION_YEARS)
    coins = sorted({s for v in lists.values() for s in v})
    CACHE.mkdir(exist_ok=True)
    for s in coins:
        f = CACHE / f"funding_{s}.json"
        if f.exists():
            continue
        rows = fetch(s)
        f.write_text(json.dumps(rows), encoding="utf-8")
        first = time.strftime("%Y-%m-%d", time.gmtime(rows[0]["t_ms"] / 1000)) if rows else "-"
        print(f"{s}: {len(rows)} rows from {first}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
