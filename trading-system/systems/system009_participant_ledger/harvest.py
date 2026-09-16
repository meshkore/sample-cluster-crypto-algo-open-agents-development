"""The deliberate download step for system 09's boundary series.

Nothing else in this package reaches the internet. The catalogue's rule is that fetching
is a separate, visible act so that no reconstruction can quietly pull a series halfway
through a run, and system 09 keeps it: `python -m system009_participant_ledger.harvest` writes into
the shared catalogue and then never runs again until someone asks for it.

Three series, and each one exists because the ledger has a hole without it:

  chain_total-bitcoins    the coin float. Sum of every cohort's holdings must equal it,
                          and it changes only by issuance. Without this the conservation
                          law has nothing to be conserved against.
  stablecoin_supply       the sector's cash faucet. Every dollar inside crypto that did
                          not arrive through an ETF arrived, in the modern era, as a
                          stablecoin mint. This is the boundary series traditional
                          finance has no equivalent of.
  etf_flow_btc            US spot BTC ETF creations and redemptions, per fund, daily,
                          in US$m, from 2024-01-11. One cohort whose behaviour is known
                          exactly - which is precisely why it is HELD OUT of the
                          reconstruction and used as the V2 anchor instead.

The ETF table is scraped from a public HTML page rather than an API. That is fragile by
nature, so the parser asserts the shape it expects and fails loudly; a silently truncated
anchor series would turn the one honest test in this MVP into a lie.
"""

from __future__ import annotations

import io
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from quantlab_catalog.paths import EXTERNAL_DIR

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_TIMEOUT = 60

BLOCKCHAIN_SUPPLY = "https://api.blockchain.info/charts/total-bitcoins?timespan=all&format=json&sampled=false"
LLAMA_STABLES = "https://stablecoins.llama.fi/stablecoincharts/all"
FARSIDE_BTC = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
BINANCE_METRICS = ("https://data.binance.vision/data/futures/um/daily/metrics/"
                   "{sym}/{sym}-metrics-{day}.zip")
#: Binance publishes the futures `metrics` archive from late 2020 and only as DAILY zips -
#: there is no monthly roll-up - so this is ~1,850 small requests for one symbol. It runs
#: once and the result is a daily series of a few hundred kilobytes.
OI_FROM = date(2020, 11, 1)

CG_CHART = ("https://api.coingecko.com/api/v3/coins/{cid}/market_chart"
            "?vs_currency=usd&days=365&interval=daily")
#: The free tier serves 365 days and refuses `days=max` with a 401. That window is enough for
#: the checkpoint the operator named - 2025-12-31 - and not enough for 2018 or 2021, which is
#: why the CoinMetrics series below exists alongside it rather than instead of it.
CM_CATALOG = ("https://community-api.coinmetrics.io/v4/catalog-v2/asset-metrics"
              "?assets={asset}&page_size=1000")
CM_METRICS = ("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
              "?assets={asset}&metrics={metrics}&frequency=1d"
              "&start_time=2013-01-01&page_size=10000")
#: CoinMetrics' community tier: full daily history, free, no key - but a DIFFERENT set of
#: metrics per asset, and asking for one the asset does not have fails the whole request with
#: a 400 or a 403. Asking the catalogue first is what took coverage from seven assets to
#: thirteen. Each of these means something different and they are kept apart on purpose:
#:
#:   SplyCur         units issued and in existence
#:   CapMrktCurUSD   that supply at the market price
#:   CapMrktEstUSD   the FREE FLOAT capitalisation - Coin Metrics' estimate with provably
#:                   lost and never-moved coins removed. For a model of who can trade what,
#:                   this is arguably the more honest denominator, and for six of our assets
#:                   it is the only one the open tier gives.
#:   PriceUSD        their reference price, which is a cross-venue composite and therefore a
#:                   useful second opinion on our single venue's close.
CM_WANTED = ("SplyCur", "CapMrktCurUSD", "CapMrktEstUSD", "PriceUSD")
CM_ASSETS = {"BTCUSDT": "btc", "ETHUSDT": "eth", "BNBUSDT": "bnb", "XRPUSDT": "xrp",
             "SOLUSDT": "sol", "TRXUSDT": "trx", "ZECUSDT": "zec", "DOGEUSDT": "doge",
             "LINKUSDT": "link", "ADAUSDT": "ada", "NEARUSDT": "near", "SUIUSDT": "sui",
             "WLDUSDT": "wld"}
CG_GLOBAL = "https://api.coingecko.com/api/v3/global"

COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}&per_page=250"
#: Binance ticker to CoinGecko id, for the laboratory's universe. Hand-maintained because a
#: symbol-to-asset mapping is exactly the kind of thing that must never be guessed: ACE is
#: Fusionist, whose id is "endurance", and an automatic match would have found a memecoin.
COINGECKO_IDS = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "BNBUSDT": "binancecoin",
    "XRPUSDT": "ripple", "SOLUSDT": "solana", "TRXUSDT": "tron", "ZECUSDT": "zcash",
    "DOGEUSDT": "dogecoin", "LINKUSDT": "chainlink", "ADAUSDT": "cardano",
    "NEARUSDT": "near", "SUIUSDT": "sui", "WLDUSDT": "worldcoin-wld",
    "ACEUSDT": "endurance",
}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return r.read()


def _write(name: str, payload) -> str:
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    path = EXTERNAL_DIR / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return f"{name:24s} {len(payload):6d} rows  {path.stat().st_size/1024:8.1f}KB"


def fetch_supply() -> str:
    """Bitcoin circulating supply, daily. Same source and shape as the other chain_ series.

    The endpoint answers at per-block resolution - nearly a million points and 38MB - and
    the ledger closes its books once a day, so this keeps the last observation of each UTC
    day. Downsampling here rather than at read time means every consumer sees the same
    series and nobody re-derives the daily grid slightly differently.
    """
    raw = json.loads(_get(BLOCKCHAIN_SUPPLY))
    daily: dict[str, float] = {}
    for pt in raw["values"]:
        day = datetime.fromtimestamp(int(pt["x"]), timezone.utc).date()
        daily[day.isoformat()] = float(pt["y"])
    rows = [{"t_s": int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp()),
             "value": v} for d, v in sorted(daily.items())]
    assert rows and rows[0]["value"] > 0 and rows[-1]["value"] > rows[0]["value"], (
        "supply must be positive and monotone; got something else")
    return _write("chain_total-bitcoins.json", rows)


def fetch_stablecoins() -> str:
    """Total stablecoin circulating supply in USD, daily, all issuers and all chains."""
    raw = json.loads(_get(LLAMA_STABLES))
    rows = [{"t_s": int(p["date"]), "value": float(p["totalCirculatingUSD"]["peggedUSD"])}
            for p in raw if p.get("totalCirculatingUSD", {}).get("peggedUSD") is not None]
    rows.sort(key=lambda r: r["t_s"])
    assert len(rows) > 2000, f"stablecoin history looks truncated: {len(rows)} rows"
    return _write("stablecoin_supply.json", rows)


_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def _cells(row_html: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)]


def _money(cell: str):
    """Farside writes negatives in accounting parentheses and blanks as a dash."""
    cell = cell.replace(",", "").strip()
    if cell in ("", "-", "\u2013"):
        return 0.0
    neg = cell.startswith("(") and cell.endswith(")")
    cell = cell.strip("()")
    try:
        v = float(cell)
    except ValueError:
        return None
    return -v if neg else v


def fetch_etf_flows() -> str:
    """Daily per-fund US spot BTC ETF flows, US$m. The V2 anchor, so it fails loudly."""
    html = _get(FARSIDE_BTC).decode("utf-8", errors="replace")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    header = None
    out = []
    for r in rows:
        c = _cells(r)
        if not c:
            continue
        if header is None and c[0] == "Date" and "Total" in c:
            header = c
            continue
        if header is None or len(c) != len(header):
            continue
        m = re.match(r"^(\d{1,2}) (\w{3}) (\d{4})$", c[0])
        if not m:
            continue                      # the 'Total' footer row and any prose rows
        day, mon, year = int(m.group(1)), _MONTHS.get(m.group(2)), int(m.group(3))
        if mon is None:
            continue
        t_s = int(datetime(year, mon, day, tzinfo=timezone.utc).timestamp())
        funds = {h: _money(v) for h, v in zip(header[1:], c[1:])}
        if funds.get("Total") is None:
            continue
        out.append({"t_s": t_s, "value": funds.pop("Total"), "funds": funds})
    out.sort(key=lambda r: r["t_s"])
    assert header is not None, "no ETF table found; the page layout changed"
    assert len(out) > 400, f"ETF history looks truncated: {len(out)} rows"
    first = datetime.fromtimestamp(out[0]["t_s"], timezone.utc).date()
    assert first.year == 2024 and first.month == 1, f"first ETF row is {first}, expected 2024-01"
    return _write("etf_flow_btc.json", out)


def _oi_day(sym: str, day: date) -> tuple[str, float, float] | None:
    """One day of open interest, averaged over its 5-minute prints.

    Returns (day, mean coins, closing coins) or None when Binance has no archive for that
    date - which happens for real gaps as well as for dates before the series begins, and
    the caller must not tell those two apart by guessing.
    """
    url = BINANCE_METRICS.format(sym=sym, day=day.isoformat())
    try:
        raw = _get(url)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            lines = z.read(z.namelist()[0]).decode().splitlines()
    except (zipfile.BadZipFile, IndexError):
        return None
    if len(lines) < 2:
        return None
    head = lines[0].split(",")
    try:
        col = head.index("sum_open_interest")
    except ValueError:
        return None
    vals = []
    for row in lines[1:]:
        parts = row.split(",")
        if len(parts) > col:
            try:
                vals.append(float(parts[col]))
            except ValueError:
                pass
    if not vals:
        return None
    return day.isoformat(), sum(vals) / len(vals), vals[-1]


def fetch_open_interest(symbol: str = "BTCUSDT", workers: int = 12) -> str:
    """Daily perpetual open interest in coins. Anchors the perp book to something observed.

    Until this series existed the levered cohort's position was a constant times a trend -
    a placeholder that could make the funding transfer run but could not make it true.
    """
    today = datetime.now(timezone.utc).date()
    days = [OI_FROM + timedelta(days=i) for i in range((today - OI_FROM).days)]
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for got in pool.map(lambda d: _oi_day(symbol, d), days):
            if got:
                day, mean, close = got
                t = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
                rows.append({"t_s": t, "value": mean, "close": close})
    rows.sort(key=lambda r: r["t_s"])
    assert len(rows) > 1200, f"open interest looks truncated: {len(rows)} days"
    return _write(f"oi_{symbol}.json", rows)


def fetch_circulating_supply() -> str:
    """Circulating supply per asset, as a SNAPSHOT.

    Bitcoin has a true daily supply series from the chain. Nothing else here does: free
    historical market-cap endpoints are limited to the last year, so the supply of every
    other asset is taken once and held constant across the record. That overstates the early
    float of anything still emitting - Solana in 2020 had less than half the supply it has
    now - and it is the largest known level error in the multi-asset ledger. It is recorded
    here, in `docs/SUMMARY.md`, and in the run's own output rather than smoothed over.
    """
    ids = ",".join(sorted(set(COINGECKO_IDS.values())))
    raw = json.loads(_get(COINGECKO_MARKETS.format(ids=ids)))
    by_id = {x["id"]: x for x in raw}
    out = {}
    for sym, cid in COINGECKO_IDS.items():
        row = by_id.get(cid)
        if row and row.get("circulating_supply"):
            out[sym] = {"coingecko_id": cid,
                        "circulating_supply": float(row["circulating_supply"]),
                        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "source": "coingecko /coins/markets snapshot, held constant"}
    missing = sorted(set(COINGECKO_IDS) - set(out))
    assert not missing, f"no circulating supply for {missing}; the ledger cannot float them"
    return _write("circulating_supply.json", out)


def _get_polite(url: str, tries: int = 6, wait: float = 12.0) -> bytes:
    """CoinGecko's free tier rate-limits hard and answers 429 rather than queueing.

    Backing off and retrying is the whole difference between a harvest that works and one
    that half-works: a partial capitalisation series would silently become a partial
    calibration, and the calibration is the thing being trusted.
    """
    import time as _time
    for attempt in range(tries):
        try:
            return _get(url)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == tries - 1:
                raise
            _time.sleep(wait * (attempt + 1))
    raise RuntimeError("unreachable")


def fetch_market_caps() -> str:
    """Published daily capitalisation, price and implied supply per asset, last 365 days.

    This is the series the whole reality-alignment initiative is measured against: the
    operator's condition is that on 2025-12-31 the model's capitalisation equals the world's,
    and until this file existed there was nothing to compare it to.

    Supply is stored as cap/price rather than taken from a supply field, deliberately - it is
    then exactly the supply that reproduces the published capitalisation at the published
    price, which is the quantity the ledger has to match. A supply from one endpoint and a cap
    from another disagree by a percent or two and there is no way to tell which is wrong.
    """
    import time as _time
    out: dict[str, dict] = {}
    for n, (sym, cid) in enumerate(sorted(COINGECKO_IDS.items())):
        if n:
            _time.sleep(8.0)
        raw = json.loads(_get_polite(CG_CHART.format(cid=cid)))
        caps, prices = raw["market_caps"], raw["prices"]
        assert len(caps) == len(prices), f"{sym}: cap and price series differ in length"
        rows = {}
        for (t, cap), (t2, px) in zip(caps, prices):
            assert t == t2, f"{sym}: cap and price timestamps diverge"
            day = datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d")
            if cap and px:
                rows[day] = {"cap": float(cap), "price": float(px),
                             "supply": float(cap) / float(px)}
        assert len(rows) > 300, f"{sym}: only {len(rows)} days of capitalisation"
        out[sym] = {"coingecko_id": cid, "days": rows}
    return _write("market_cap_1y.json", out)


def _cm_available(asset: str) -> list[str]:
    """Which of the wanted metrics this asset actually has daily, in the OPEN tier.

    The `community` flag matters: the catalogue lists metrics the paid tier serves too, and
    requesting one of those is a 403 that takes the whole asset down with it.
    """
    raw = json.loads(_get(CM_CATALOG.format(asset=asset)))
    rows = (raw.get("data") or [{}])[0].get("metrics", [])
    out = []
    for m in rows:
        if m["metric"] in CM_WANTED and any(
                f["frequency"] == "1d" and f.get("community") for f in m["frequencies"]):
            out.append(m["metric"])
    return out


def fetch_deep_market_caps() -> str:
    """Full daily supply, capitalisation and reference price, from CoinMetrics' open tier.

    The point of this one is the early record. v1 carries TODAY'S supply backwards across
    eight years, which floats too many coins in every year before the last - measured at
    2025-12-31 that is +35% of Worldcoin and +31% of Fusionist, and it gets worse the further
    back you look. This is the series that replaces the assumption.

    What comes back differs per asset, so each asset's row says which metrics it carries
    rather than pretending to a common schema.
    """
    out: dict[str, dict] = {}
    for sym, asset in sorted(CM_ASSETS.items()):
        metrics = _cm_available(asset)
        if not metrics:
            continue
        raw = json.loads(_get(CM_METRICS.format(asset=asset, metrics=",".join(metrics))))
        rows = {}
        for r in raw.get("data", []):
            vals = {m: float(r[m]) for m in metrics if r.get(m)}
            if vals:
                rows[r["time"][:10]] = vals
        assert len(rows) > 200, f"{sym}: only {len(rows)} days from CoinMetrics"
        out[sym] = {"coinmetrics_asset": asset, "metrics": metrics, "days": rows}
    uncovered = sorted(set(COINGECKO_IDS) - set(out))
    return _write("market_cap_full.json", {"assets": out, "uncovered": uncovered})


def fetch_global_cap() -> str:
    """The published capitalisation of the whole market, today.

    Only the current reading is free - the historical global chart is a paid endpoint - so
    this pins the scope error at one date rather than through time. The calibration says so
    where it uses it; a number whose vintage is not stated is the kind of thing this
    laboratory has been burned by before.
    """
    raw = json.loads(_get(CG_GLOBAL))["data"]
    return _write("global_market_cap.json", {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "total_market_cap_usd": float(raw["total_market_cap"]["usd"]),
        "total_volume_usd": float(raw["total_volume"]["usd"]),
        "btc_dominance_pct": float(raw["market_cap_percentage"]["btc"]),
        "active_cryptocurrencies": raw.get("active_cryptocurrencies"),
        "source": "coingecko /global, current reading only - history is a paid endpoint"})


def main() -> int:
    for fn in (fetch_supply, fetch_stablecoins, fetch_etf_flows, fetch_circulating_supply,
               fetch_market_caps, fetch_deep_market_caps, fetch_global_cap,
               fetch_open_interest):
        try:
            print("  OK  ", fn())
        except Exception as exc:                       # noqa: BLE001 - report, do not hide
            print(f"  FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
            return 1
    print("\nwritten to", EXTERNAL_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
