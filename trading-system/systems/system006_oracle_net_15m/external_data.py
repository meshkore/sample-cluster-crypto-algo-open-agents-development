"""New-information acquisition: perp funding history + the real Fear & Greed index.

The refutation ledger closed every price-derived generation lever (P13/P15/P16/
P17/A61), and two built modules have been waiting for honest data feeds:
`microstructure` (funding/OI crowding) and `sentiment` (real crowd emotion vs the
current price proxy). Both sources here are public, free, and point-in-time:

  - Binance USD-M funding rates (8h cadence, per symbol, from perp listing on) -
    the crowd-positioning signal. fundingTime is the settlement timestamp; a bar
    may only read settlements STRICTLY BEFORE it (the consumer's job).
  - alternative.me Fear & Greed (daily since 2018-02) - published each morning;
    a bar may only read values whose day is strictly past (the consumer's job).

This module only FETCHES and STORES, verbatim plus a parsed copy - timestamps
original, no resampling, no fills. Files land in the SHARED catalogue at
backtester/data/external/ (quantlab_catalog owns the location)
(gitignored: re-downloadable data, never committed). Research-only; no keys,
no account, public endpoints.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=1000&startTime={start}"
FNG_URL = "https://api.alternative.me/fng/?limit=0"
# On-chain daily series (blockchain.info). Free, long-history, published daily with the
# day's own timestamp, so a bar may read only days strictly before it - the same causal
# rule the Fear & Greed feed follows. These describe NETWORK USE rather than price:
#   n-unique-addresses  how many addresses transacted - adoption/activity
#   n-transactions      settlement demand
#   hash-rate           miner commitment, the slowest-moving conviction there is
#   miners-revenue      what that commitment is being paid
CHAIN_URL = "https://api.blockchain.info/charts/{name}?timespan=all&format=json"
CHAIN_SERIES = ("n-unique-addresses", "n-transactions", "hash-rate", "miners-revenue")
from quantlab_catalog.paths import EXTERNAL_DIR

# The shared catalogue owns the location now (operator, 2026-09-08: every downloaded
# series belongs to the common catalogue, not to whichever system happened to fetch it).
OUT_DIR = EXTERNAL_DIR


def _get(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310 - fixed https hosts
        return json.loads(r.read().decode("utf-8"))


def fetch_funding(symbol: str, start_ms: int = 1_500_000_000_000,
                  pause: float = 0.35) -> list[dict]:
    """All funding settlements for one perp symbol, oldest first. Empty if unlisted."""
    rows: list[dict] = []
    cursor = start_ms
    while True:
        batch = _get(FUNDING_URL.format(sym=symbol, start=cursor))
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        last = int(batch[-1]["fundingTime"])
        if len(batch) < 1000:
            break
        cursor = last + 1
        time.sleep(pause)  # public rate limits deserve manners
    seen = set()
    out = []
    for r in rows:
        t = int(r["fundingTime"])
        if t not in seen:
            seen.add(t)
            out.append({"t_ms": t, "rate": float(r["fundingRate"])})
    return sorted(out, key=lambda r: r["t_ms"])


def fetch_feargreed() -> list[dict]:
    """Full daily Fear & Greed history, oldest first."""
    doc = _get(FNG_URL)
    rows = [{"t_s": int(d["timestamp"]), "value": int(d["value"]),
             "label": d.get("value_classification")} for d in doc.get("data", [])]
    return sorted(rows, key=lambda r: r["t_s"])


def fetch_chain(name: str) -> list[dict]:
    """One daily on-chain series, oldest first, timestamps as published."""
    doc = _get(CHAIN_URL.format(name=name))
    return sorted(({"t_s": int(v["x"]), "value": float(v["y"])} for v in doc.get("values", [])),
                  key=lambda r: r["t_s"])


def harvest(symbols: list[str], out_dir: Path = OUT_DIR,
            pause_chain: float = 1.0) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, int] = {}
    for sym in symbols:
        rows = fetch_funding(sym)
        (out_dir / f"funding_{sym}.json").write_text(json.dumps(rows), encoding="utf-8")
        report[sym] = len(rows)
        print(f"funding {sym}: {len(rows)} settlements"
              + (f" ({rows[0]['t_ms']} .. {rows[-1]['t_ms']})" if rows else " (no perp)"),
              flush=True)
    for name in CHAIN_SERIES:
        try:
            rows = fetch_chain(name)
            (out_dir / f"chain_{name}.json").write_text(json.dumps(rows), encoding="utf-8")
            report[name] = len(rows)
            print(f"chain {name}: {len(rows)} days", flush=True)
        except Exception as exc:  # noqa: BLE001 - one missing series must not stop the rest
            print(f"chain {name}: FAILED ({exc})", flush=True)
        time.sleep(pause_chain)
    fng = fetch_feargreed()
    (out_dir / "feargreed.json").write_text(json.dumps(fng), encoding="utf-8")
    report["feargreed"] = len(fng)
    print(f"feargreed: {len(fng)} days", flush=True)
    (out_dir / "harvest_report.json").write_text(
        json.dumps(report, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    from system006_oracle_net_15m import universe
    harvest(universe.load())
