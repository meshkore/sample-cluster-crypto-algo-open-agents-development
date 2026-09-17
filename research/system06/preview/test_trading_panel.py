"""The Trading area shows the book: value, drawdown, positions, orders, spreads.

Operator, 2026-09-17: *"in live trading you can see the asset's price, the price of the
portfolio, the list of orders we have executed, with their profits."* So this drives the
real page with a synthetic live payload of exactly the shape the trader publishes, and
asserts that each of those four things is on screen with a number next to it.

A synthetic payload rather than the live one on purpose: this must fail when the PAGE
breaks, not when the market is closed or the trader has not started.

    python research/system06/preview/test_trading_panel.py
"""

from __future__ import annotations

import functools
import http.server
import json
import pathlib
import socketserver
import sys
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parents[3]
PAGE = REPO / "research/system06/preview/dashboard.html"

LIVE = {
    "at": "2026-09-17T09:15:04+00:00",
    "mode": "paper",
    "halted": None,
    "cutover": "2026-09-17T09:00:00+00:00",
    "trading_since": "2026-09-17T09:00:00+00:00",
    "engine": {"version": "v1-champion-192x3", "system": "system006_oracle_net_15m",
               "band": {"enter": 0.75, "exit_": 0.25, "min_hold": 16},
               "risk": {"max_positions": 2, "position_fraction": 0.15,
                        "stop_loss": 0.08, "trail_stop": 0.12},
               "metrics": {"sealed_2026_return": 0.2571},
               "signals_at": "2026-09-17T09:14:40+00:00",
               "overlays_at": "2026-09-17T09:02:00+00:00"},
    "account": {"initial_capital": 100000.0, "equity": 100842.11, "cash": 85320.4,
                "invested": 15521.71, "exposure": 0.1539, "return_pct": 0.0084,
                "drawdown": 0.0031, "high_water": 101155.0, "realised": 312.55,
                "fees_paid": 41.2, "trades_closed": 3, "win_rate": 0.6667},
    "positions": [{"symbol": "BTCUSDT", "quantity": 0.10231, "entry_price": 75880.2,
                   "entry_time": "2026-09-17T09:00:00+00:00", "price": 76425.35,
                   "value": 7819.9, "unrealised_pct": 0.00718}],
    "prices": [{"symbol": "BTCUSDT", "bid": 76425.34, "ask": 76425.35, "mid": 76425.345,
                "spread_bps": 0.001},
               {"symbol": "ETHUSDT", "bid": 2543.11, "ask": 2543.2, "mid": 2543.155,
                "spread_bps": 0.354}],
    "orders": [{"kind": "FILL", "at": "2026-09-17T09:00:12+00:00", "symbol": "BTCUSDT",
                "side": "BUY", "quantity": 0.10231, "price": 75880.2, "notional": 7763.0,
                "fee": 7.76, "reason": "prob 0.81 trend up", "realised": None,
                "slippage_bps": 0.6},
               {"kind": "FILL", "at": "2026-09-16T18:45:02+00:00", "symbol": "SOLUSDT",
                "side": "SELL", "quantity": 42.0, "price": 132.4, "notional": 5560.8,
                "fee": 5.56, "reason": "exit band", "realised": 190.22,
                "slippage_bps": 1.2}],
    "last_bar": "2026-09-17T09:00:00+00:00",
    "last_note": "1 open, 1 order",
    "orders_this_bar": 1,
    "fills_this_bar": [],
    "equity_curve": [{"at": "2026-09-17T09:00:00+00:00", "equity": 100000.0},
                     {"at": "2026-09-17T09:15:00+00:00", "equity": 100842.11}],
}


def _serve(directory: pathlib.Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main() -> int:
    sys.path.insert(0, str(PAGE.parent))
    import mock_server
    from playwright.sync_api import sync_playwright

    state = mock_server._state()
    state["live"] = LIVE                      # as if the trader had just published

    errors: list[str] = []
    httpd, port = _serve(PAGE.parent)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/api/state", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(state, default=str)))
        for route in ("**/api/knowledge", "**/api/iterations", "**/api/systems"):
            page.route(route, lambda r: r.fulfill(status=200,
                                                  content_type="application/json", body="{}"))
        page.route("**/api/detail**", lambda r: r.fulfill(status=200,
                                                         content_type="application/json", body="{}"))
        page.goto(f"http://127.0.0.1:{port}/{PAGE.name}")
        page.wait_for_function("typeof STATE !== 'undefined' && STATE && STATE.live",
                               timeout=10000)
        page.evaluate("setView('trading')")
        page.wait_for_selector("#tradingBody .kpi .kt", timeout=8000)

        tiles = page.query_selector_all("#tradingBody .kpi .kt")
        assert len(tiles) == 4, f"expected four trading tiles, found {len(tiles)}"
        hero = page.inner_text("#tradingBody .kpi .kt.hero")
        assert "$100,842.11" in hero, f"the portfolio value is not on screen: {hero!r}"
        print(f"  portfolio tile: {hero.splitlines()[1] if len(hero.splitlines())>1 else hero}")

        body = page.inner_text("#tradingBody")
        for want in ("BTCUSDT", "76425", "190.22", "v1-champion-192x3", "0.15"):
            assert want in body, f"the trading panel does not show {want!r}"
        assert "SELL" in body and "BUY" in body, "the order list does not show both sides"
        print("  positions, live book, orders with profit, engine chips: all present")

        # The whole point of the area is figures, not prose.
        digits = sum(c.isdigit() for c in body)
        assert digits >= 200, f"only {digits} digits on the trading floor"
        print(f"  trading body: {digits} digits")

        # And the empty case must say so rather than rendering a broken panel.
        page.evaluate("STATE.live = null; renderTrading()")
        empty = page.inner_text("#tradingBody")
        assert "not started" in empty.lower(), f"the empty state is wrong: {empty[:120]!r}"
        print("  empty state is honest")

        browser.close()
    httpd.shutdown()

    assert not errors, "the page threw:\n  " + "\n  ".join(errors[:6])
    print("trading panel: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
