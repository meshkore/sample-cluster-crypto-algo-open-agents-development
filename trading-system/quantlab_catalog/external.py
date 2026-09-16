"""Everything in the catalogue that is not a price candle.

Four families, all public, all free, all already downloaded on this machine:

  funding      Binance USD-M perpetual funding rates, 8h cadence, per symbol.
               The crowd-positioning signal. `fundingTime` is the SETTLEMENT
               timestamp - a bar may only read settlements strictly before it.
  feargreed    alternative.me Fear & Greed, daily from 2018-02. Published each
               morning; a bar may only read days strictly past.
  onchain      blockchain.info daily series - unique addresses, transactions,
               hash rate, miners' revenue. Network USE rather than price, which is
               the only reason they are here: they are not another moving average
               of the thing we are trying to predict.
  stablecoins  DefiLlama total stablecoin float in USD, daily from 2017-11. The cash
               BOUNDARY of the crypto sector: dollars enter and leave through mints and
               burns, never through trades.
  etfflow      US spot BTC ETF creations and redemptions per fund, US$m, daily from
               2024-01. The one cohort whose behaviour is public.
  reference    FRED daily macro - NASDAQ, VIX, 2y and 10y yields, the 2s10s curve,
               the broad dollar, WTI. Non-revised series only, each with a MEASURED
               publication delay in `system006_oracle_net_15m.reference.SERIES_LAG_DAYS`.

THE ONE RULE THAT MATTERS, and it is the consumer's job rather than this module's:
every one of these is published LATE. This module hands back the series with its own
timestamps untouched and applies no lag, no resample and no fill, because a helper that
silently shifted a series would be indistinguishable from a helper that leaked the
future. `reference.py` is where the measured delays live and where a test fails if
reality drifts past what is assumed.

Nothing here downloads. `system006_oracle_net_15m.external_data.harvest` fetches; this reads.
That separation is why no backtest in this laboratory can reach the internet halfway
through a run.
"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import EXTERNAL_DIR, external_file

# family -> (filename pattern, one line on what it is)
EXTERNAL_SERIES: dict[str, tuple[str, str]] = {
    "funding": ("funding_{symbol}.json", "Binance perp funding, 8h, per symbol"),
    "feargreed": ("feargreed.json", "alternative.me Fear & Greed, daily from 2018-02"),
    "onchain": ("chain_{name}.json", "blockchain.info daily network series"),
    "reference": ("reference_markets.json", "FRED daily macro, non-revised only"),
    "stablecoins": ("stablecoin_supply.json", "DefiLlama total stablecoin float, USD, daily"),
    "etfflow": ("etf_flow_btc.json", "US spot BTC ETF creations/redemptions, US$m, daily"),
    "openinterest": ("oi_{symbol}.json", "Binance perp open interest, daily, per symbol"),
    "supply": ("circulating_supply.json", "Circulating supply per universe symbol, snapshot"),
}
ONCHAIN_SERIES = ("n-unique-addresses", "n-transactions", "hash-rate", "miners-revenue",
                  "total-bitcoins")


def _read(path: Path):
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is not in the catalogue. Run the harvest deliberately - nothing "
            f"in quantlab_catalog downloads.")
    return json.loads(path.read_text(encoding="utf-8"))


def funding(symbol: str) -> list[dict]:
    """Funding settlements for one symbol, verbatim, ascending by `fundingTime`."""
    return _read(external_file(f"funding_{symbol}.json"))


def feargreed() -> list[dict]:
    return _read(external_file("feargreed.json"))


def onchain(name: str) -> list[dict]:
    if name not in ONCHAIN_SERIES:
        raise ValueError(f"unknown on-chain series {name!r}; have {ONCHAIN_SERIES}")
    return _read(external_file(f"chain_{name}.json"))


def stablecoins() -> list[dict]:
    """Total stablecoin float in USD, daily, all issuers and all chains.

    The crypto sector's cash boundary. A trade moves dollars between participants and
    changes no total; a mint is one of the few events that changes how many dollars are
    inside the sector at all, which is why this series - and not trading volume - is what
    the ledger reads when it asks how much money came in.
    """
    return _read(external_file("stablecoin_supply.json"))


def etf_flows() -> list[dict]:
    """Daily US spot BTC ETF net flow in US$m, with the per-fund split under `funds`.

    From 2024-01-11. Exactly one cohort of the market whose behaviour is published, which
    makes it far more valuable as something to PREDICT than as something to consume.
    """
    return _read(external_file("etf_flow_btc.json"))


def open_interest(symbol: str) -> list[dict]:
    """Daily perpetual open interest in coins, with the day's mean and close.

    Positioning, not price. Open interest is the only free series that pins how large the
    leveraged cohort's book actually is; without it a model of leverage is a constant times
    a trend.
    """
    return _read(external_file(f"oi_{symbol}.json"))


def market_cap_1y() -> dict:
    """Published daily capitalisation, price and implied supply per asset, last 365 days.

    The yardstick for system 09's V5 calibration: the model's capitalisation has to equal
    this one. CoinGecko's free tier serves exactly a year, which covers 2025-12-31.
    """
    return _read(external_file("market_cap_1y.json"))


def market_cap_full() -> dict:
    """Full-history capitalisation and TRUE circulating supply, CoinMetrics open tier.

    Covers seven of the fourteen; the `uncovered` key names the rest, because a calibration
    that quietly skipped them would look better than it is.
    """
    return _read(external_file("market_cap_full.json"))


def global_market_cap() -> dict:
    """The whole market's capitalisation, as of the harvest date only. History is paid."""
    return _read(external_file("global_market_cap.json"))


def circulating_supply() -> dict:
    """Circulating supply per symbol, as a snapshot. Bitcoin also has a true daily series in
    `onchain("total-bitcoins")`; nothing else does, and the difference matters."""
    return _read(external_file("circulating_supply.json"))


def reference_markets() -> dict:
    """The FRED bundle, keyed by series id, each with its own `rows` of [date, value]."""
    return _read(external_file("reference_markets.json"))


def series_status() -> dict[str, dict]:
    """What is present, how big, and where it was found. Used by `inventory`.

    Reports the LOCATION as well as the size because the difference between a
    catalogue path and a legacy one is the difference between migrated and not, and a
    machine can be half-migrated without anything failing.
    """
    out: dict[str, dict] = {}
    seen: set[Path] = set()
    for fam, (pattern, what) in EXTERNAL_SERIES.items():
        if fam == "openinterest":
            files = sorted(EXTERNAL_DIR.glob("oi_*.json"))
        elif "{symbol}" in pattern:
            files = sorted(EXTERNAL_DIR.glob("funding_*.json"))
            legacy = [p for p in (external_file(f"funding_{s}.json")
                                  for s in _known_funding_symbols()) if p.is_file()]
            files = sorted({*files, *legacy})
        elif fam in ("stablecoins", "etfflow", "supply"):
            q = external_file(pattern)
            files = [q] if q.is_file() else []
        elif "{name}" in pattern:
            files = [external_file(f"chain_{n}.json") for n in ONCHAIN_SERIES]
            files = [p for p in files if p.is_file()]
        else:
            p = external_file(pattern)
            files = [p] if p.is_file() else []
        seen.update(files)
        out[fam] = {
            "what": what,
            "files": len(files),
            "bytes": sum(p.stat().st_size for p in files),
            "in_catalogue": all(EXTERNAL_DIR in p.parents for p in files) if files else None,
            "example": str(files[0]) if files else None,
        }
    return out


def _known_funding_symbols() -> list[str]:
    """Symbols with a funding file, discovered from disk rather than declared.

    A hard-coded list would go stale the first time the universe is re-selected, and
    would then report a symbol as missing data when the truth is that nobody looked.
    """
    names: set[str] = set()
    for root in (EXTERNAL_DIR, external_file("funding_BTCUSDT.json").parent):
        if root.is_dir():
            names.update(p.name[len("funding_"):-len(".json")]
                         for p in root.glob("funding_*.json"))
    return sorted(names)
