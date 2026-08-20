"""The tradable universe: liquid USDT spot pairs, stablecoins excluded.

The laboratory's constraints are explicit — crypto only, and "fiat, stablecoin
and commodity-backed pairs are excluded at the source", with a capacity floor of
USD 10M daily turnover so a USD 10,000 order is absorbable at the 0.1%
participation cap. This picks exactly that set from Binance's live turnover, so
the universe is re-selected from the market rather than hard-coded, and writes it
to disk so a training run and its forward test read the same list.

A snapshot, deliberately: the universe moves, but a run must be reproducible, so
the list is frozen to a file and re-selected only when we choose to.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

EXCHANGE_INFO = "https://api.binance.com/api/v3/exchangeInfo"
TICKER_24H = "https://api.binance.com/api/v3/ticker/24hr"
KLINES = "https://api.binance.com/api/v3/klines"

# Excluded at the source: stablecoins and wrapped/fiat-backed tokens whose USDT
# pair is a currency peg, not a crypto price. Matched on the base asset.
STABLE_BASES = {
    "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "UST", "USTC", "USDD",
    "USD1", "RLUSD", "USDE", "USDS", "GUSD", "LUSD", "PYUSD", "EURC",
    "EUR", "GBP", "AEUR", "EURI", "PAXG", "XAUT", "WBTC", "WBETH", "BETH",
}

DEFAULT_MIN_TURNOVER = 10_000_000.0
# History old enough to train on. This is also the cleanest filter against two
# kinds of noise a turnover screen lets through: tokenised stocks (SanDisk,
# SpaceX and the like, which trade on Binance with deep volume but are not
# crypto) and days-old pump listings. Both have almost no history; an
# established crypto has years. So "listed before ~18 months ago" removes them
# without a fragile name blacklist.
DEFAULT_MIN_HISTORY_DAYS = 540
DEFAULT_PATH = "research/system06/universe.json"


def _get(url: str) -> object:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read())


def _history_days(symbol: str) -> float:
    """Age of the oldest 15m candle, in days. One cheap call per candidate."""
    url = f"{KLINES}?symbol={symbol}&interval=1d&startTime=0&limit=1"
    rows = _get(url)
    if not rows:
        return 0.0
    first_ms = int(rows[0][0])
    now_ms = int(_get(f"{KLINES}?symbol={symbol}&interval=1d&limit=1")[0][0])
    return (now_ms - first_ms) / 86_400_000.0


def liquid_universe(
    min_turnover: float = DEFAULT_MIN_TURNOVER,
    min_history_days: float = DEFAULT_MIN_HISTORY_DAYS,
) -> list[str]:
    """USDT spot pairs that are liquid, established, and not stablecoins.

    Three screens, each removing a distinct kind of thing that is not a tradable
    crypto with a trainable history: the turnover floor, the stablecoin/wrapped
    exclusion, and a minimum listing age that drops tokenised stocks and fresh
    pump listings.
    """
    info = _get(EXCHANGE_INFO)
    tradable = [
        s["symbol"]
        for s in info["symbols"]
        if s["symbol"].endswith("USDT")
        and s["status"] == "TRADING"
        and s.get("isSpotTradingAllowed")
        and s["baseAsset"] not in STABLE_BASES
    ]
    turnover = {t["symbol"]: float(t["quoteVolume"]) for t in _get(TICKER_24H)}
    liquid = sorted(
        (s for s in tradable if turnover.get(s, 0.0) >= min_turnover),
        key=lambda s: turnover.get(s, 0.0),
        reverse=True,
    )
    established = []
    for symbol in liquid:
        try:
            if _history_days(symbol) >= min_history_days:
                established.append(symbol)
        except Exception:
            continue  # a symbol we cannot age is one we do not trust
    return established


def load(path: str | Path = DEFAULT_PATH) -> list[str]:
    """The frozen universe from disk. Falls back to BTCUSDT if none is saved."""
    p = Path(path)
    if p.is_file():
        return list(json.loads(p.read_text())["symbols"])
    return ["BTCUSDT"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--min-turnover", type=float, default=DEFAULT_MIN_TURNOVER)
    parser.add_argument("--min-history-days", type=float, default=DEFAULT_MIN_HISTORY_DAYS)
    parser.add_argument("--out", default=DEFAULT_PATH)
    args = parser.parse_args(argv)

    symbols = liquid_universe(args.min_turnover, args.min_history_days)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {
            "min_turnover": args.min_turnover,
            "min_history_days": args.min_history_days,
            "count": len(symbols),
            "symbols": symbols,
        },
        indent=2,
    ))
    print(f"{len(symbols)} symbols >= ${args.min_turnover:,.0f} turnover -> {out}")
    print(", ".join(symbols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
