"""THE REGISTRY: what exists in the world, where it comes from, and how late it arrives.

This file is code and it is committed. The observations it describes are not - they live
under `backtester/data/world/` and are re-downloadable. The split is deliberate: a
disagreement about whether the Federal Reserve's balance sheet is nine days late should be a
reviewable diff, not an argument, and it should not be buried in a data file nobody reads.

THE ONE RULE THIS MODULE ENFORCES
A stream cannot be registered without a publication lag. There is no default. A default would
be zero, zero is a lie for every series that is released after the period it describes, and a
model trained on that lie reads the future and looks brilliant. `Stream.__post_init__` raises.

THE THREE LAG REGIMES, named rather than blurred:

    observed    the source publishes a real release timestamp - news, ALFRED vintages, the
                daily ETF flow reports. Use it verbatim; there is no modelling here.
    estimated   the source gives only the latest revision, so known_at = ref_date + lag, with
                the lag measured where system 06 measured it and set to at least the release
                cadence where it did not. Conservative on purpose: a week late is a cost, a
                day early is a corrupted result.
    assumed     the observation IS the event - a closing price, a block, a funding settlement -
                so it is knowable at its own timestamp. Lag zero, declared, so that zero is a
                decision.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

# --------------------------------------------------------------------------- taxonomy
CATEGORIES = (
    "rates", "inflation", "money", "credit", "fx", "equity", "commodity", "activity",
    "crypto_price", "crypto_supply", "crypto_onchain", "crypto_flow", "crypto_deriv",
    "sentiment", "attention", "policy", "regulation", "security_incident", "adoption",
)
REGIONS = ("US", "EZ", "DE", "UK", "JP", "CN", "IN", "BR", "KR", "TR", "AR", "ZA",
           "CA", "AU", "CH", "global", "offshore")
FREQUENCIES = ("D", "B", "W", "M", "Q", "A", "irregular")
TRANSFORMS = ("level", "diff", "log_change", "pct_change", "percentile", "zscore",
              "ratio", "real_rate", "spread", "yoy")
VINTAGE_MODES = ("observed", "estimated", "assumed")


@dataclass(frozen=True)
class Stream:
    """One series, fully described. Everything a consumer needs before it reads a number."""

    id: str                      # `us.cpi.headline` - region.subject.detail, lowercase, dotted
    title: str
    category: str
    region: str
    unit: str                    # "pct", "index", "usd", "usd_bn", "coins", "ratio", "count"
    freq: str
    lag_days: int | None         # publication delay; None is an ERROR, not a default
    vintage: str                 # observed | estimated | assumed
    source: str                  # where it came from, specifically enough to re-fetch
    reader: str                  # dotted name of the adapter in `adapters.py`
    reader_args: tuple = ()
    transform: str = "level"     # what `panel` applies unless told otherwise
    revised: bool = False        # true when we hold only the LATEST revision of a revised series
    #: What `ref_date` points at. "point" - the stamp IS the moment described (a closing
    #: price, the balance sheet on a Wednesday, a yield). "period_start" - the stamp is the
    #: first day of a period the number summarises, so the number cannot exist until the
    #: period ENDS. FRED stamps every monthly series at the first of the month, which means
    #: `lag` alone made February's CPI knowable on 19 February. It is published in March.
    stamped: str = "point"
    #: How long a reading may go on standing for "today" before the stream is treated as
    #: having nothing to say. None derives it from the frequency.
    #:
    #: This exists because of a measured failure, not a hypothetical one. FRED stopped
    #: mirroring the OECD's national inflation series: Japan's ends in June 2021, Korea's in
    #: November 2023, and most of the rest in March 2025. An as-of reader carries the last
    #: observation forward indefinitely, so without this guard a model evaluating 2026 would
    #: be fed Japan's inflation rate from five years earlier as though it were current - and
    #: a constant column across a whole era is the most reliable way ever found to teach a
    #: model the calendar.
    max_stale_days: int | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.lag_days is None:
            raise ValueError(
                f"stream {self.id!r} has no publication lag. There is no default: a series "
                "released after the period it describes and read on its reference date is a "
                "leak. Measure it, or set it to the release cadence and mark it estimated.")
        for value, allowed, what in ((self.category, CATEGORIES, "category"),
                                     (self.region, REGIONS, "region"),
                                     (self.freq, FREQUENCIES, "frequency"),
                                     (self.transform, TRANSFORMS, "transform"),
                                     (self.vintage, VINTAGE_MODES, "vintage mode")):
            if value not in allowed:
                raise ValueError(f"stream {self.id!r}: unknown {what} {value!r}")
        if self.stamped not in ("point", "period_start"):
            raise ValueError(f"stream {self.id!r}: unknown stamp {self.stamped!r}")
        if self.vintage == "assumed" and self.lag_days != 0:
            raise ValueError(f"stream {self.id!r}: 'assumed' means knowable at its own "
                             f"timestamp, so the lag must be 0, not {self.lag_days}")

    @property
    def stale_after(self) -> int:
        """Days after which a reading stops being allowed to speak for the present."""
        if self.max_stale_days is not None:
            return self.max_stale_days
        # Measured from `known_at`, so the allowance has to cover the publication delay as
        # well as the gap between releases - otherwise a series with a thirty-day lag and a
        # weekly cadence is "expired" on the day it arrives, which is how M2 first failed.
        base = {"D": 10, "B": 10, "W": 24, "M": 75, "Q": 200, "A": 550,
                "irregular": 400}[self.freq]
        return base + (self.lag_days or 0)

    def period_end(self, ref: str) -> date:
        """The last day the observation describes. Equal to the stamp for a point series."""
        d = date.fromisoformat(ref[:10])
        if self.stamped == "point":
            return d
        if self.freq == "M":
            nxt = date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
            return nxt - timedelta(days=1)
        return d + timedelta(days={"W": 6, "Q": 91, "A": 364}.get(self.freq, 0))

    def known_at(self, ref: str) -> str:
        """When this observation became knowable, as a date string.

        Two steps, and the first one is the one that is always forgotten: wait for the period
        to END, then wait for the publisher. `lag_days` is therefore measured from the end of
        the reference period, which is also how every statistical office quotes it - "released
        on the thirteenth working day of the following month".

        For `observed` streams the store carries a real release date per row and this is only
        the fallback. For everything else it is the whole of the clock.
        """
        if self.lag_days == 0 and self.stamped == "point":
            return ref
        return (self.period_end(ref) + timedelta(days=self.lag_days)).isoformat()


# ---------------------------------------------------------------- the FRED lag table
#: Measured where system 06 measured it; otherwise at least the release cadence. Monthly
#: national statistics are the worst offenders: a CPI print for March lands in mid-April, and
#: for several of the OECD-sourced national series FRED itself is a further week behind.
_FRED_LAG = {
    "WALCL": 9, "RRPONTSYD": 2, "WM2NS": 30, "DFF": 2,
    "DGS2": 6, "DGS10": 6, "T10Y2Y": 4, "DTWEXBGS": 14,
    "VIXCLS": 6, "NASDAQCOM": 4, "SP500": 4, "DCOILWTICO": 10, "DEXUSEU": 6,
    "BAMLH0A0HYM2": 6, "BAA10Y": 6, "STLFSI4": 10, "NIKKEI225": 4,
    "DEXCHUS": 6, "DEXJPUS": 6, "DEXUSUK": 6, "DEXBZUS": 6, "DEXINUS": 6, "DEXSFUS": 6,
    # Monthly figures: days after the month ENDS, which is how the release calendars are
    # written. US CPI lands on about the thirteenth of the following month; the OECD-sourced
    # national series reach FRED considerably later, so they are given a conservative month.
    "CPIAUCSL": 14, "CPILFESL": 14,
    "CP0000EZ19M086NEST": 20,                # Eurostat HICP final
    "CHNCPIALLMINMEI": 40, "JPNCPIALLMINMEI": 40, "INDCPIALLMINMEI": 40,
    "BRACPIALLMINMEI": 40, "GBRCPIALLMINMEI": 40, "TURCPIALLMINMEI": 40,
    "ZAFCPIALLMINMEI": 40,
    "ECBDFR": 3, "IRLTLT01JPM156N": 40, "IRLTLT01GBM156N": 40, "INTDSRCNM193N": 40,
}

#: FRED id -> (stream id, category, region, unit, frequency, default transform)
_FRED_MAP = {
    "WALCL":        ("us.fed.balance_sheet", "money", "US", "usd_mn", "W", "log_change"),
    "RRPONTSYD":    ("us.fed.reverse_repo", "money", "US", "usd_bn", "D", "log_change"),
    "WM2NS":        ("us.money.m2", "money", "US", "usd_bn", "W", "log_change"),
    "DFF":          ("us.rate.policy", "rates", "US", "pct", "D", "level"),
    "DGS2":         ("us.rate.2y", "rates", "US", "pct", "B", "level"),
    "DGS10":        ("us.rate.10y", "rates", "US", "pct", "B", "level"),
    "T10Y2Y":       ("us.rate.curve_10y2y", "rates", "US", "pct", "B", "level"),
    "DTWEXBGS":     ("us.fx.dollar_broad", "fx", "US", "index", "B", "log_change"),
    "VIXCLS":       ("us.equity.vix", "sentiment", "US", "index", "B", "percentile"),
    # FRED serves only the last three years of the ICE BofA high-yield spread - a licence
    # window, measured on 2026-09-15, not something a different request can fix. It stays
    # registered because it is the sharpest version of the signal where it exists, and the
    # two below carry the same channel across the whole record.
    "BAMLH0A0HYM2": ("us.credit.hy_spread", "credit", "US", "pct", "B", "diff"),
    "BAA10Y": ("us.credit.baa_spread", "credit", "US", "pct", "B", "diff"),
    "STLFSI4": ("us.credit.stress_index", "credit", "US", "index", "W", "percentile"),
    "SP500":        ("us.equity.spx", "equity", "US", "index", "B", "log_change"),
    "NASDAQCOM":    ("us.equity.nasdaq", "equity", "US", "index", "B", "log_change"),
    "DCOILWTICO":   ("global.commodity.oil_wti", "commodity", "global", "usd", "B", "log_change"),
    "NIKKEI225":    ("jp.equity.nikkei", "equity", "JP", "index", "B", "log_change"),
    # --- inflation, by region. The operator's point: a holder in Frankfurt, one in Shanghai
    # and one in Istanbul are not making the same decision, and one global CPI cannot say so.
    "CPIAUCSL":           ("us.cpi.headline", "inflation", "US", "index", "M", "yoy"),
    "CPILFESL":           ("us.cpi.core", "inflation", "US", "index", "M", "yoy"),
    "CP0000EZ19M086NEST": ("ez.cpi.headline", "inflation", "EZ", "index", "M", "yoy"),
    "CHNCPIALLMINMEI":    ("cn.cpi.headline", "inflation", "CN", "index", "M", "yoy"),
    "JPNCPIALLMINMEI":    ("jp.cpi.headline", "inflation", "JP", "index", "M", "yoy"),
    "INDCPIALLMINMEI":    ("in.cpi.headline", "inflation", "IN", "index", "M", "yoy"),
    "BRACPIALLMINMEI":    ("br.cpi.headline", "inflation", "BR", "index", "M", "yoy"),
    "GBRCPIALLMINMEI":    ("uk.cpi.headline", "inflation", "UK", "index", "M", "yoy"),
    "TURCPIALLMINMEI":    ("tr.cpi.headline", "inflation", "TR", "index", "M", "yoy"),
    "ZAFCPIALLMINMEI":    ("za.cpi.headline", "inflation", "ZA", "index", "M", "yoy"),
    # --- rates elsewhere, so a real rate can be computed per region rather than per planet.
    "ECBDFR":          ("ez.rate.policy", "rates", "EZ", "pct", "D", "level"),
    "IRLTLT01JPM156N": ("jp.rate.10y", "rates", "JP", "pct", "M", "level"),
    "IRLTLT01GBM156N": ("uk.rate.10y", "rates", "UK", "pct", "M", "level"),
    "INTDSRCNM193N":   ("cn.rate.discount", "rates", "CN", "pct", "M", "level"),
    # --- the currency each of those investors actually earns in.
    "DEXCHUS": ("cn.fx.usdcny", "fx", "CN", "rate", "B", "log_change"),
    "DEXJPUS": ("jp.fx.usdjpy", "fx", "JP", "rate", "B", "log_change"),
    "DEXUSUK": ("uk.fx.gbpusd", "fx", "UK", "rate", "B", "log_change"),
    "DEXBZUS": ("br.fx.usdbrl", "fx", "BR", "rate", "B", "log_change"),
    "DEXINUS": ("in.fx.usdinr", "fx", "IN", "rate", "B", "log_change"),
    "DEXSFUS": ("za.fx.usdzar", "fx", "ZA", "rate", "B", "log_change"),
    "DEXUSEU": ("ez.fx.eurusd", "fx", "EZ", "rate", "B", "log_change"),
}

#: Monthly national statistics are revised; daily market quotes are not.
_REVISED_FREQS = ("M", "Q", "A", "W")

# ------------------------------------------------------------------ crypto-native streams
_ONCHAIN = {
    "n-unique-addresses": ("crypto.btc.addresses", "count", "users active on the chain"),
    "n-transactions":     ("crypto.btc.transactions", "count", "chain throughput"),
    "hash-rate":          ("crypto.btc.hashrate", "index", "the cost of the network's security"),
    "miners-revenue":     ("crypto.btc.miner_revenue", "usd", "the largest structural seller"),
    "total-bitcoins":     ("crypto.btc.supply", "coins", "issued supply"),
}

#: IMF monthly CPI via DBnomics: country -> (stream id, region). These REPLACE the FRED
#: mirrors for everywhere except the US and the euro area, because the mirrors are dead - see
#: `ingest/dbnomics.py` for the measurement. They are themselves about a year behind, which
#: the staleness guard reports rather than papers over.
_IMF_CPI = {
    "JP": ("jp.cpi.imf", "JP"), "CN": ("cn.cpi.imf", "CN"), "IN": ("in.cpi.imf", "IN"),
    "BR": ("br.cpi.imf", "BR"), "ZA": ("za.cpi.imf", "ZA"), "KR": ("kr.cpi.imf", "KR"),
    "TR": ("tr.cpi.imf", "TR"), "GB": ("uk.cpi.imf", "UK"), "CA": ("ca.cpi.imf", "CA"),
    "US": ("us.cpi.imf", "US"),
}

_FUNDING_SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "ADAUSDT",
                    "DOGEUSDT", "TRXUSDT", "LINKUSDT", "NEARUSDT", "SUIUSDT", "WLDUSDT",
                    "ZECUSDT", "ACEUSDT")


@functools.lru_cache(maxsize=1)
def registry() -> dict[str, Stream]:
    """Every stream this archive knows about, built once.

    Nothing is read from disk here. A stream exists in the registry whether or not its data
    has been harvested; `inventory` is what reports the difference, and reporting the
    difference out loud is the point - a catalogue that lets you believe in data it does not
    have is worse than no catalogue.
    """
    out: dict[str, Stream] = {}

    def add(s: Stream) -> None:
        if s.id in out:
            raise ValueError(f"duplicate stream id {s.id!r}")
        out[s.id] = s

    for fred_id, (sid, cat_, region, unit, freq, tr) in _FRED_MAP.items():
        add(Stream(id=sid, title=fred_id, category=cat_, region=region, unit=unit, freq=freq,
                   lag_days=_FRED_LAG[fred_id], vintage="estimated",
                   source=f"FRED:{fred_id}", reader="fred", reader_args=(fred_id,),
                   transform=tr, revised=freq in _REVISED_FREQS,
                   # FRED stamps a monthly figure on the first of the month it describes.
                   # Weekly series here are point snapshots (the balance sheet ON a
                   # Wednesday), so only the monthly ones wait for a period to close.
                   stamped="period_start" if freq in ("M", "Q", "A") else "point",
                   note="latest revision only; no vintages held"))

    for cc, (sid, region) in _IMF_CPI.items():
        add(Stream(id=sid, title=f"IMF monthly CPI index, {cc}", category="inflation",
                   region=region, unit="index", freq="M",
                   # The IMF publishes about six weeks after the month closes, and DBnomics
                   # mirrors it a little later still; sixty days is the conservative read.
                   lag_days=60, vintage="estimated", source=f"IMF/CPI M.{cc}.PCPI_IX",
                   reader="raw", reader_args=("dbnomics", f"imf_cpi_{cc}"),
                   transform="yoy", revised=True, stamped="period_start",
                   note="replaces the discontinued FRED/OECD mirror for this country"))

    add(Stream(id="crypto.sentiment.feargreed", title="Crypto Fear & Greed index",
               category="sentiment", region="global", unit="index", freq="D",
               lag_days=0, vintage="assumed", source="alternative.me",
               reader="feargreed", transform="level",
               note="the one published series that measures the crowd directly"))

    for name, (sid, unit, why) in _ONCHAIN.items():
        add(Stream(id=sid, title=name, category="crypto_onchain", region="global", unit=unit,
                   freq="D", lag_days=1, vintage="estimated", source=f"blockchain.com:{name}",
                   reader="onchain", reader_args=(name,), transform="log_change", note=why))

    add(Stream(id="crypto.stablecoin.supply", title="Stablecoin supply",
               category="crypto_flow", region="global", unit="usd", freq="D",
               lag_days=1, vintage="estimated", source="catalogue:stablecoin_supply",
               reader="stablecoins", transform="log_change",
               note="the clearest observable of money waiting at the boundary"))
    add(Stream(id="crypto.etf.btc_flow", title="US spot Bitcoin ETF net flow",
               category="crypto_flow", region="US", unit="usd_mn", freq="B",
               lag_days=1, vintage="observed", source="catalogue:etf_flow_btc",
               reader="etf_flows", transform="level",
               note="reported the next morning; the only regulated flow we can see directly"))
    add(Stream(id="crypto.btc.open_interest", title="BTC perpetual open interest",
               category="crypto_deriv", region="global", unit="btc", freq="D",
               lag_days=0, vintage="assumed", source="binance", reader="open_interest",
               reader_args=("BTCUSDT",), transform="log_change"))
    add(Stream(id="crypto.global.market_cap", title="Total crypto market capitalisation",
               category="crypto_price", region="global", unit="usd", freq="D",
               lag_days=0, vintage="assumed", source="reconstructed from tape x float",
               reader="global_cap", transform="log_change",
               note="reconstructed rather than downloaded: CoinGecko's history is paid"))

    for sym in _FUNDING_SYMBOLS:
        add(Stream(id=f"crypto.{sym[:-4].lower()}.funding", title=f"{sym} perp funding",
                   category="crypto_deriv", region="global", unit="rate", freq="D",
                   lag_days=0, vintage="assumed", source=f"binance:{sym}",
                   reader="funding", reader_args=(sym,), transform="level",
                   note="settled three times a day; the price of being leveraged long"))
        add(Stream(id=f"crypto.{sym[:-4].lower()}.price", title=f"{sym} daily close",
                   category="crypto_price", region="global", unit="usd", freq="D",
                   lag_days=0, vintage="assumed", source=f"binance:{sym} 15m -> daily close",
                   reader="price", reader_args=(sym,), transform="log_change"))

    return out


def by_category(name: str) -> list[str]:
    return sorted(s.id for s in registry().values() if s.category == name)


def by_region(name: str) -> list[str]:
    return sorted(s.id for s in registry().values() if s.region == name)


def get(stream_id: str) -> Stream:
    try:
        return registry()[stream_id]
    except KeyError:
        raise KeyError(f"unknown stream {stream_id!r}; "
                       f"{len(registry())} are registered, see `inventory`") from None
