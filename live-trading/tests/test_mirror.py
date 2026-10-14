"""The BingX mirror's refusals and its arithmetic, against a fake venue (no network).

Run: `python -m pytest live-trading/tests -q`
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone

import pytest

from quantlab_live import mirror as M
from quantlab_live.brokers import bingx as B


class FakeVenue:
    """Order book at fixed prices; records every order it is asked to send."""

    private = True

    def __init__(self, prices, perms=(1, 2), balances=None):
        self.prices = prices
        self.perms = list(perms)
        self.sent = []
        self.bal = balances or {"USDT": 1e9}

    def sync_time(self):
        return 0

    def permissions(self):
        return {"permissions": self.perms, "ipAddresses": []}

    def filters(self):
        return {B.venue_symbol(s): {"minNotional": 1, "stepSize": 0.001, "apiStateBuy": True} for s in self.prices}

    def book(self, s):
        p = self.prices[s]
        return p * 0.9995, p * 1.0005

    def depth(self, s):
        bid, ask = self.book(s)
        return [(bid, 1e9)], [(ask, 1e9)]

    def balances(self):
        return self.bal

    def market_buy(self, s, quote, cid):
        self.sent.append(("BUY", s, quote))
        q = quote / self.book(s)[1]
        self.bal[B.base_asset(s)] = self.bal.get(B.base_asset(s), 0) + q
        return {"orderId": len(self.sent), "executedQty": q, "cummulativeQuoteQty": quote,
                "status": "FILLED", "fee": quote * 0.001, "feeAsset": "USDT"}

    def market_sell(self, s, qty, cid):
        self.sent.append(("SELL", s, qty))
        return {"orderId": len(self.sent), "executedQty": qty, "cummulativeQuoteQty": qty * self.book(s)[0],
                "status": "FILLED", "fee": qty * self.book(s)[0] * 0.001, "feeAsset": "USDT"}

    def query(self, s, oid):
        raise B.VenueError(0, "use the order reply")


def paper(positions, equity=50_000.0):
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "account": {"equity": equity},
            "positions": [{"symbol": s, "value": v, "price": 100.0} for s, v in positions.items()]}


ON = {"trading": "on", "reachable": True}
OFF = {"trading": "off", "reachable": True}
OK = {"recommendation": "trade"}
ARM = {"venue": "bingx", "capital": 1000, "max_order": 400, "real_money": True}


@pytest.fixture(autouse=True)
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(M.C, "STATE_DIR", tmp_path)
    monkeypatch.setattr(M, "STATE", tmp_path / "mirror_state.json")
    monkeypatch.setattr(M, "LEDGER", tmp_path / "orders.jsonl")
    monkeypatch.setattr(M, "HALT", tmp_path / "HALT")
    monkeypatch.setattr(M, "ARM", tmp_path / "arm.json")
    monkeypatch.setattr(M, "remote_switch", lambda: ON)
    monkeypatch.setattr(M.time, "sleep", lambda s: None)


def test_signature_is_hmac_of_the_sorted_query():
    v = B.BingX("k", "secret")
    seen = {}
    v._http = lambda method, path, query, headers=None: seen.update(q=query, h=headers) or {"code": 0, "data": {}}
    v._signed("GET", "/x", symbol="BTC-USDT", side="BUY")
    query, sig = seen["q"].rsplit("&signature=", 1)
    keys = [kv.split("=")[0] for kv in query.split("&")]
    assert keys == sorted(keys)
    assert sig == hmac.new(b"secret", query.encode(), hashlib.sha256).hexdigest()
    assert seen["h"] == {"X-BX-APIKEY": "k"}


def test_a_key_that_can_withdraw_is_refused(tmp_path):
    M.ARM.write_text('{"venue": "bingx", "capital": 1000, "real_money": true}')
    assert M.decide_mode(FakeVenue({}, perms=(1, 2, 5)))[0] == "shadow"
    assert M.decide_mode(FakeVenue({}, perms=(1, 2)))[0] == "live"


def test_no_arming_file_means_shadow():
    assert M.decide_mode(FakeVenue({}))[:2] == ("shadow", "not armed (no arming file)")


def test_live_follows_paper_weights_with_its_own_capital():
    v = FakeVenue({"BTCUSDT": 100.0, "ETHUSDT": 10.0})
    r = M.cycle(v, "live", ARM, "", paper({"BTCUSDT": 10_000, "ETHUSDT": 5_000}), ON, OK, execute=True)
    buys = {s: q for side, s, q in v.sent if side == "BUY"}
    assert buys["BTCUSDT"] == pytest.approx(200, rel=0.01)    # 20% of $1,000
    assert buys["ETHUSDT"] == pytest.approx(100, rel=0.01)
    assert r["book"]["cash"] == pytest.approx(1000 - 300 - 0.3, rel=1e-3)


def test_switch_off_sends_nothing_live_but_shadow_still_measures():
    v = FakeVenue({"BTCUSDT": 100.0})
    M.cycle(v, "live", ARM, "", paper({"BTCUSDT": 10_000}), OFF, OK, execute=True)
    assert v.sent == []
    r = M.cycle(v, "shadow", {}, "", paper({"BTCUSDT": 10_000}), OFF, OK, execute=True)
    assert r["sent"] and "live would not send" in r["can"]["reasons"][0]


def test_switch_flipped_off_mid_cycle_stops_the_rest(monkeypatch):
    v = FakeVenue({"BTCUSDT": 100.0, "ETHUSDT": 10.0})
    reads = iter([ON, OFF, OFF])
    monkeypatch.setattr(M, "remote_switch", lambda: next(reads))
    r = M.cycle(v, "live", ARM, "", paper({"BTCUSDT": 10_000, "ETHUSDT": 5_000}), ON, OK, execute=True)
    assert len(v.sent) == 1 and any("switch went off" in n for n in r["notes"])


def test_local_halt_file_stops_live():
    M.HALT.write_text("operator")
    v = FakeVenue({"BTCUSDT": 100.0})
    M.cycle(v, "live", ARM, "", paper({"BTCUSDT": 10_000}), ON, OK, execute=True)
    assert v.sent == []


def test_health_halt_sells_everything_and_buys_nothing():
    v = FakeVenue({"BTCUSDT": 100.0, "ETHUSDT": 10.0})
    M.cycle(v, "live", ARM, "", paper({"BTCUSDT": 10_000}), ON, OK, execute=True)
    v.sent.clear()
    r = M.cycle(v, "live", ARM, "", paper({"BTCUSDT": 10_000, "ETHUSDT": 5_000}), ON,
                {"recommendation": "halt"}, execute=True)
    assert [s[0] for s in v.sent] == ["SELL"] and r["book"]["holdings"] == {}


def test_health_block_entries_keeps_positions_but_no_buys():
    v = FakeVenue({"BTCUSDT": 100.0, "ETHUSDT": 10.0})
    M.cycle(v, "live", ARM, "", paper({"BTCUSDT": 10_000}), ON, OK, execute=True)
    v.sent.clear()
    M.cycle(v, "live", ARM, "", paper({"BTCUSDT": 10_000, "ETHUSDT": 5_000}), ON,
            {"recommendation": "block_entries"}, execute=True)
    assert v.sent == []


def test_stale_paper_book_is_not_traded():
    v = FakeVenue({"BTCUSDT": 100.0})
    p = paper({"BTCUSDT": 10_000})
    p["at"] = "2026-01-01T00:00:00+00:00"
    M.cycle(v, "live", ARM, "", p, ON, OK, execute=True)
    assert v.sent == []


def test_book_never_believes_itself_over_the_venue():
    v = FakeVenue({"BTCUSDT": 100.0})
    M.cycle(v, "live", ARM, "", paper({"BTCUSDT": 10_000}), ON, OK, execute=True)
    v.bal["BTC"] = 0.5          # someone sold by hand
    r = M.cycle(v, "live", ARM, "", paper({"BTCUSDT": 10_000}), ON, OK, execute=False)
    assert r["book"]["holdings"]["BTCUSDT"] == 0.5 and r["notes"]


def test_drawdown_breaker_writes_halt():
    v = FakeVenue({"BTCUSDT": 100.0})
    M.cycle(v, "live", {**ARM, "max_drawdown": 0.10}, "", paper({"BTCUSDT": 50_000}), ON, OK, execute=True)
    v.prices["BTCUSDT"] = 50.0
    v.sent.clear()
    M.cycle(v, "live", {**ARM, "max_drawdown": 0.10}, "", paper({"BTCUSDT": 50_000}), ON, OK, execute=True)
    assert M.HALT.exists() and v.sent == []


def test_step_rounding_and_book_walk():
    assert B.round_step(1.23456, 0.01) == 1.23
    assert B.round_step(0.00001234, 1e-6) == 0.000012
    px, q = B.walk_book([(10.0, 1.0), (11.0, 10.0)], notional=21.0)
    assert q == pytest.approx(2.0) and px == pytest.approx(10.5)


def test_advisory_health_does_not_stop_trading(tmp_path, monkeypatch):
    hp = tmp_path / "health.json"
    hp.write_text('{"at": "%s", "recommendation": "halt", "thresholds": {"enforced": false}}'
                  % datetime.now(timezone.utc).isoformat(timespec="seconds"))
    monkeypatch.setattr(M, "HEALTH", hp)
    h = M.health()
    assert h["recommendation"] == "trade" and h["advice"] == "halt"
    hp.write_text(hp.read_text().replace("false", "true"))
    assert M.health()["recommendation"] == "halt"
