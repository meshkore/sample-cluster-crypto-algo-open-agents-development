"""BingX spot REST client: market data, balances and market orders. Nothing else.

Operator, 2026-10-14: *"I'm preparing the trading system to operate live ... with an API key
and real funds"* - on BingX, where the account already is.

What this file does NOT do, on purpose: withdrawals, transfers, futures, leverage, limit
orders that could rest forgotten on the book. Spot, market orders, long only.

Signing (BingX v1 spot): every private parameter plus `timestamp` (ms, corrected by the
server clock) is sorted by key and joined as `k=v&k=v`; the HMAC-SHA256 hex digest of that
string with the secret goes in `signature`, and the key in the `X-BX-APIKEY` header. The
signed query string is never logged: it would not leak the secret, but it does carry the
key's request and there is nothing to gain from writing it down.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://open-api.bingx.com"
UA = "Mozilla/5.0 (quantlab-live)"
RECV_WINDOW = 5000

# Key permissions as BingX numbers them. A key that can move money OUT is refused.
PERM_SPOT_TRADE = 1
PERM_READ = 2
PERM_TRANSFER = 4
PERM_WITHDRAW = 5
FORBIDDEN_PERMS = {PERM_TRANSFER, PERM_WITHDRAW}


class VenueError(RuntimeError):
    """The venue answered with an error code. Carries the code and BingX's message only."""

    def __init__(self, code, msg: str):
        super().__init__(f"BingX {code}: {msg}")
        self.code = code


def venue_symbol(symbol: str) -> str:
    """The lab's `BTCUSDT` is BingX's `BTC-USDT`."""
    return symbol[:-4] + "-USDT" if symbol.endswith("USDT") and "-" not in symbol else symbol


def base_asset(symbol: str) -> str:
    return venue_symbol(symbol).split("-")[0]


class BingX:
    def __init__(self, api_key: str | None = None, api_secret: str | None = None,
                 timeout: float = 15.0, base: str = BASE):
        self._key = api_key or ""
        self._secret = api_secret or ""
        self.timeout = timeout
        self.base = base
        self._offset_ms = 0
        self._filters: dict[str, dict] | None = None

    @property
    def private(self) -> bool:
        return bool(self._key and self._secret)

    # -- transport ---------------------------------------------------------------

    def _http(self, method: str, path: str, query: str = "", headers: dict | None = None) -> dict:
        url = f"{self.base}{path}" + (f"?{query}" if query else "")
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                doc = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise VenueError(e.code, e.read().decode("utf-8", "replace")[:300]) from None
        if not isinstance(doc, dict):
            raise VenueError("?", "unexpected response")
        if doc.get("code") not in (0, None):
            raise VenueError(doc.get("code"), str(doc.get("msg", ""))[:300])
        return doc

    def _public(self, path: str, **params) -> dict:
        q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        return self._http("GET", path, q)

    def _signed(self, method: str, path: str, **params) -> dict:
        if not self.private:
            raise VenueError("nokey", "no API key loaded")
        params = {k: v for k, v in params.items() if v is not None}
        params["recvWindow"] = RECV_WINDOW
        params["timestamp"] = int(time.time() * 1000) + self._offset_ms
        query = "&".join(f"{k}={params[k]}" for k in sorted(params))
        sig = hmac.new(self._secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return self._http(method, path, f"{query}&signature={sig}", {"X-BX-APIKEY": self._key})

    def sync_time(self) -> int:
        """Align our timestamps with the server clock; returns the offset in ms."""
        t0 = time.time() * 1000
        server = int(self._public("/openApi/swap/v2/server/time")["data"]["serverTime"])
        self._offset_ms = int(server - (t0 + time.time() * 1000) / 2)
        return self._offset_ms

    # -- market data -------------------------------------------------------------

    def filters(self, refresh: bool = False) -> dict[str, dict]:
        """Per venue symbol: minNotional, stepSize, tickSize, whether the API may buy/sell."""
        if self._filters is None or refresh:
            rows = self._public("/openApi/spot/v1/common/symbols")["data"]["symbols"]
            self._filters = {r["symbol"]: r for r in rows}
        return self._filters

    def book(self, symbol: str) -> tuple[float, float]:
        """Best bid and ask."""
        d = self._public("/openApi/spot/v1/ticker/bookTicker", symbol=venue_symbol(symbol))["data"][0]
        return float(d["bidPrice"]), float(d["askPrice"])

    def depth(self, symbol: str, limit: int = 50) -> tuple[list, list]:
        """Bids high->low and asks low->high as [(price, qty)]."""
        d = self._public("/openApi/spot/v1/market/depth", symbol=venue_symbol(symbol), limit=limit)["data"]
        bids = sorted(((float(p), float(q)) for p, q in d["bids"]), reverse=True)
        asks = sorted((float(p), float(q)) for p, q in d["asks"])
        return bids, asks

    # -- account -----------------------------------------------------------------

    def permissions(self) -> dict:
        """{'permissions': [int], 'ipAddresses': [str]} for the loaded key."""
        d = self._signed("GET", "/openApi/v1/account/apiPermissions")
        return d.get("data", d)

    def balances(self) -> dict[str, float]:
        """Free balance per asset on the spot account."""
        rows = self._signed("GET", "/openApi/spot/v1/account/balance")["data"]["balances"]
        return {r["asset"]: float(r["free"]) for r in rows}

    # -- orders --------------------------------------------------------------------

    def market_buy(self, symbol: str, quote_usdt: float, client_id: str) -> dict:
        """Spend `quote_usdt` USDT at market."""
        return self._signed("POST", "/openApi/spot/v1/trade/order", symbol=venue_symbol(symbol),
                            side="BUY", type="MARKET", quoteOrderQty=f"{quote_usdt:.2f}",
                            newClientOrderId=client_id)["data"]

    def market_sell(self, symbol: str, quantity: float, client_id: str) -> dict:
        """Sell `quantity` (already rounded to the step size) at market."""
        return self._signed("POST", "/openApi/spot/v1/trade/order", symbol=venue_symbol(symbol),
                            side="SELL", type="MARKET", quantity=_fmt(quantity),
                            newClientOrderId=client_id)["data"]

    def query(self, symbol: str, order_id) -> dict:
        return self._signed("GET", "/openApi/spot/v1/trade/query", symbol=venue_symbol(symbol),
                            orderId=order_id)["data"]


def _fmt(x: float) -> str:
    """A decimal string without exponent notation (BingX rejects `1e-05`)."""
    return f"{x:.10f}".rstrip("0").rstrip(".")


def round_step(qty: float, step: float) -> float:
    """Round a quantity DOWN to the venue's step size."""
    if step <= 0:
        return qty
    n = int(qty / step + 1e-9)
    return float(_fmt(n * step))


def walk_book(levels: list[tuple[float, float]], notional: float | None = None,
              quantity: float | None = None) -> tuple[float, float]:
    """Average price and filled quantity for a market order walking `levels`.

    Give `notional` (USDT to spend, buys) or `quantity` (to sell). If the visible book is
    too thin the remainder is priced at the last level - optimistic, so the shadow book
    also records how much of the order the visible depth covered.
    """
    spent = got = 0.0
    for price, size in levels:
        if notional is not None:
            take = min(size, (notional - spent) / price)
        else:
            take = min(size, quantity - got)
        if take <= 0:
            break
        spent += take * price
        got += take
    last = levels[-1][0] if levels else 0.0
    if notional is not None and spent < notional and last:
        got += (notional - spent) / last
        spent = notional
    elif quantity is not None and got < quantity and last:
        spent += (quantity - got) * last
        got = quantity
    return (spent / got if got else 0.0), got
