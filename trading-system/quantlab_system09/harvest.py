"""The deliberate download step for system 09's boundary series.

Nothing else in this package reaches the internet. The catalogue's rule is that fetching
is a separate, visible act so that no reconstruction can quietly pull a series halfway
through a run, and system 09 keeps it: `python -m quantlab_system09.harvest` writes into
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

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

from quantlab_catalog.paths import EXTERNAL_DIR

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_TIMEOUT = 60

BLOCKCHAIN_SUPPLY = "https://api.blockchain.info/charts/total-bitcoins?timespan=all&format=json&sampled=false"
LLAMA_STABLES = "https://stablecoins.llama.fi/stablecoincharts/all"
FARSIDE_BTC = "https://farside.co.uk/bitcoin-etf-flow-all-data/"


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


def main() -> int:
    for fn in (fetch_supply, fetch_stablecoins, fetch_etf_flows):
        try:
            print("  OK  ", fn())
        except Exception as exc:                       # noqa: BLE001 - report, do not hide
            print(f"  FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
            return 1
    print("\nwritten to", EXTERNAL_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
