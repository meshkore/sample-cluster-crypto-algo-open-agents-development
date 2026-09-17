"""Live market data: candles as they close, and the book as it stands.

Public endpoints only - no key is needed to read prices, and the live layer deliberately
runs the whole paper stack without ever touching a credential.

Two things this module is careful about, both of which produce silent, plausible, wrong
results if you get them wrong:

* **A candle is only usable once it is CLOSED.** Binance returns the forming candle as
  the last element of `/klines`, with a close price that is simply the last trade. A
  backtest never sees such a bar, so feeding one to the brain would be a look-ahead of
  up to fifteen minutes in the wrong direction - the decision would be made on a price
  that has not settled. `closed_bars` drops it, always.
* **The book is the fill price, not the candle.** The candle close is where the last
  trade happened; a buy pays the ask and a sell receives the bid. The difference is the
  spread, which is exactly what the operator asked to be measured rather than assumed.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from quantlab_backtester.models import Bar

BINANCE = "https://api.binance.com"
USER_AGENT = "quantlab-live/1.0"


class FeedError(RuntimeError):
    """The feed could not answer. Never swallowed: a trader that cannot see must stop."""


@dataclass(frozen=True)
class Quote:
    """The top of the book at an instant, with the spread already worked out."""

    symbol: str
    bid: float
    ask: float
    bid_qty: float
    ask_qty: float
    at: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        mid = self.mid
        return 0.0 if mid <= 0 else 10_000.0 * (self.ask - self.bid) / mid


def _get(url: str, timeout: float = 15.0, retries: int = 3):
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last = exc
            # A venue hiccup is normal and a trader that dies on one is useless; a venue
            # that is still down after three tries is news the caller has to handle.
            time.sleep(1.5 * (attempt + 1))
    raise FeedError(f"{url}: {type(last).__name__}: {last}")


class BinanceFeed:
    """Closed candles and live quotes for a list of symbols."""

    def __init__(self, base: str = BINANCE, interval: str = "15m"):
        self.base = base.rstrip("/")
        self.interval = interval

    # -- candles ---------------------------------------------------------------

    def closed_bars(self, symbol: str, limit: int = 500,
                    end_time: datetime | None = None) -> list[Bar]:
        """The last `limit` CLOSED candles, oldest first. The forming one is dropped."""
        url = (f"{self.base}/api/v3/klines?symbol={symbol}"
               f"&interval={self.interval}&limit={min(int(limit), 1000)}")
        if end_time is not None:
            url += f"&endTime={int(end_time.timestamp() * 1000)}"
        rows = _get(url)
        now_ms = time.time() * 1000
        bars: list[Bar] = []
        for row in rows:
            open_ms, close_ms = int(row[0]), int(row[6])
            if close_ms > now_ms:
                continue  # still forming: not a bar yet
            bars.append(Bar(
                timestamp=datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc),
                open=float(row[1]), high=float(row[2]), low=float(row[3]),
                close=float(row[4]), volume=float(row[5]),
                taker_buy_volume=float(row[9]) if len(row) > 9 else None,
            ))
        return bars

    def history(self, symbol: str, bars_wanted: int) -> list[Bar]:
        """Walk backwards in pages until `bars_wanted` closed candles are in hand."""
        out: list[Bar] = []
        end: datetime | None = None
        seen: set[datetime] = set()
        while len(out) < bars_wanted:
            page = self.closed_bars(symbol, limit=1000, end_time=end)
            fresh = [b for b in page if b.timestamp not in seen]
            if not fresh:
                break
            seen.update(b.timestamp for b in fresh)
            out = fresh + out
            end = fresh[0].timestamp
        return sorted(out, key=lambda b: b.timestamp)[-bars_wanted:]

    # -- the book --------------------------------------------------------------

    def quote(self, symbol: str) -> Quote:
        data = _get(f"{self.base}/api/v3/ticker/bookTicker?symbol={symbol}")
        return Quote(symbol=symbol, bid=float(data["bidPrice"]), ask=float(data["askPrice"]),
                     bid_qty=float(data["bidQty"]), ask_qty=float(data["askQty"]),
                     at=datetime.now(timezone.utc))

    def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Every symbol's top of book in ONE request, so the prices share an instant.

        Marking a portfolio with quotes fetched one at a time spreads the valuation over
        seconds of moving market; the batch endpoint returns them all from the same
        snapshot, which is what an equity figure is supposed to mean.
        """
        wanted = set(symbols)
        rows = _get(f"{self.base}/api/v3/ticker/bookTicker")
        at = datetime.now(timezone.utc)
        out: dict[str, Quote] = {}
        for row in rows:
            if row.get("symbol") in wanted:
                out[row["symbol"]] = Quote(
                    symbol=row["symbol"], bid=float(row["bidPrice"]), ask=float(row["askPrice"]),
                    bid_qty=float(row["bidQty"]), ask_qty=float(row["askQty"]), at=at)
        missing = wanted - set(out)
        if missing:
            raise FeedError(f"no book for {sorted(missing)}")
        return out

    def server_time(self) -> datetime:
        data = _get(f"{self.base}/api/v3/time")
        return datetime.fromtimestamp(int(data["serverTime"]) / 1000, tz=timezone.utc)
