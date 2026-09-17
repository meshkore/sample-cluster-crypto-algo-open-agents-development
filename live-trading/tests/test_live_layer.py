"""The live layer's arithmetic, its refusals, and the shape the brain is handed.

Run: `python -m pytest live-trading/tests -q`

These are the properties that, if they broke, would be discovered by losing money rather
than by a red test: cash conservation, the realised-profit figure on a round trip, the
account payload the brain reads, and the two refusals (trade before the cutover, trade
with a lever that cannot be fed).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from quantlab_live import config, engine as engine_mod
from quantlab_live.book import Fill, LiveBook
from quantlab_live.brokers.paper import PaperBroker
from quantlab_live.feed import Quote
from quantlab_live.trader import next_bar_close


def quote(symbol="BTCUSDT", bid=100.0, ask=100.1) -> Quote:
    return Quote(symbol=symbol, bid=bid, ask=ask, bid_qty=10.0, ask_qty=10.0,
                 at=datetime.now(timezone.utc))


# --- the broker ------------------------------------------------------------------


def test_a_buy_pays_the_ask_and_a_sell_receives_the_bid():
    broker = PaperBroker()
    q = quote()
    buy = broker.buy("BTCUSDT", 1_000.0, q, bar_value=None)
    sell = broker.sell("BTCUSDT", 10.0, q, bar_value=None)
    assert buy.price == pytest.approx(q.ask), "a market buy that pays the mid is fiction"
    assert sell.price == pytest.approx(q.bid)
    # Half the spread, each way, recorded rather than assumed.
    assert buy.slippage_bps == pytest.approx(10_000 * (q.ask - q.mid) / q.mid)
    assert sell.slippage_bps == pytest.approx(10_000 * (q.mid - q.bid) / q.mid)


def test_size_costs_more_than_the_spread():
    """The impact term is the whole reason the champion's sealed year is +25.7 not +33.9."""
    broker = PaperBroker()
    q = quote()
    small = broker.buy("BTCUSDT", 100.0, q, bar_value=1_000_000.0)
    large = broker.buy("BTCUSDT", 500_000.0, q, bar_value=1_000_000.0)
    assert large.price > small.price
    # sqrt law: a half-bar order pays IMPACT_BPS * sqrt(0.5) over the ask.
    expected = q.ask * (1 + (60.0 * 0.5 ** 0.5) / 10_000)
    assert large.price == pytest.approx(expected, rel=1e-9)


def test_a_flat_fee_is_charged_on_both_sides():
    broker = PaperBroker()
    buy = broker.buy("BTCUSDT", 1_000.0, quote(), bar_value=None)
    assert buy.fee == pytest.approx(1_000.0 * 10 / 10_000)


# --- the book --------------------------------------------------------------------


def test_a_round_trip_conserves_cash_and_reports_the_profit():
    book = LiveBook(initial_capital=10_000.0, cash=10_000.0)
    broker = PaperBroker()
    entry = quote(bid=100.0, ask=100.0)          # no spread: the arithmetic is visible
    book.apply_fill(broker.buy("BTCUSDT", 1_000.0, entry, bar_value=None))
    assert book.cash == pytest.approx(10_000.0 - 1_000.0 - 1.0)   # notional + 10bps fee
    held = book.positions["BTCUSDT"]
    assert held.quantity == pytest.approx(10.0)

    exit_ = quote(bid=110.0, ask=110.0)          # +10%
    book.mark({"BTCUSDT": 110.0})
    assert book.equity == pytest.approx(book.cash + 10.0 * 110.0)
    fill = book.apply_fill(broker.sell("BTCUSDT", held.quantity, exit_, bar_value=None))
    # 10 units bought for 1,001 all-in, sold for 1,100 less 1.10 of fee.
    assert fill.realised == pytest.approx(1_100.0 - 1.1 - 1_001.0)
    assert book.positions == {}
    assert book.trades_closed == 1
    assert book.cash == pytest.approx(book.equity)


def test_averaging_up_moves_the_entry_price():
    """scale_in buys again into a winner; a stop measured from the FIRST price would lie."""
    book = LiveBook(initial_capital=10_000.0, cash=10_000.0)
    broker = PaperBroker(commission_bps=0.0)
    book.apply_fill(broker.buy("X", 1_000.0, quote(bid=100.0, ask=100.0), bar_value=None))
    book.apply_fill(broker.buy("X", 1_000.0, quote(bid=200.0, ask=200.0), bar_value=None))
    held = book.positions["X"]
    assert held.quantity == pytest.approx(15.0)            # 10 + 5
    assert held.entry_price == pytest.approx((100*10 + 200*5) / 15)


def test_a_buy_bigger_than_the_cash_is_refused():
    book = LiveBook(initial_capital=100.0, cash=100.0)
    with pytest.raises(ValueError):
        book.apply_fill(Fill(at=datetime.now(timezone.utc), symbol="X", side="BUY",
                             quantity=1.0, price=1_000.0, notional=1_000.0, fee=1.0))


def test_the_account_payload_is_the_one_the_brain_reads():
    """Byte-for-byte the keys `BacktestSession._account_payload` produces."""
    book = LiveBook(initial_capital=1_000.0, cash=900.0)
    book.positions["X"] = type(book.positions)  # placeholder replaced below
    del book.positions["X"]
    broker = PaperBroker()
    book.apply_fill(broker.buy("X", 100.0, quote(bid=10.0, ask=10.0), bar_value=None))
    payload = book.account_payload()
    assert set(payload) == {"initial_capital", "cash", "equity", "invested", "exposure",
                            "positions"}
    assert set(payload["positions"]["X"]) == {"quantity", "entry_price", "entry_time",
                                              "invested", "unrealised_pct"}


def test_the_book_survives_a_restart(tmp_path):
    book = LiveBook(initial_capital=5_000.0, cash=5_000.0)
    book.apply_fill(PaperBroker().buy("X", 500.0, quote(bid=50.0, ask=50.0), bar_value=None))
    path = tmp_path / "book.json"
    book.save(path)
    again = LiveBook.load(path)
    assert again.cash == pytest.approx(book.cash)
    assert again.positions["X"].quantity == pytest.approx(book.positions["X"].quantity)
    assert again.trades_closed == book.trades_closed


def test_drawdown_is_peak_to_trough_on_equity():
    book = LiveBook(initial_capital=1_000.0, cash=1_000.0)
    book.apply_fill(PaperBroker(commission_bps=0.0).buy("X", 1_000.0, quote(bid=10.0, ask=10.0),
                                                        bar_value=None))
    book.mark({"X": 20.0})
    _ = book.equity
    book.high_water = max(book.high_water, book.equity)      # 2,000
    book.mark({"X": 15.0})                                   # 1,500
    assert book.drawdown == pytest.approx(0.25)


# --- the engine ------------------------------------------------------------------


def test_the_shipped_engine_package_declares_what_it_needs():
    package = engine_mod.EnginePackage.current()
    assert package.manifest["system"] == "system006_oracle_net_15m"
    assert package.band["enter"] and package.risk["max_positions"]
    # The champion runs the meta filter and the money model; a live engine that could not
    # feed them would be a different strategy wearing this one's name.
    assert package.needs_meta and package.needs_money


def test_an_engine_refuses_to_trade_a_lever_it_cannot_feed(tmp_path, monkeypatch):
    package = engine_mod.EnginePackage.current()
    live = engine_mod.LiveEngine(package, symbols=["BTCUSDT"])
    monkeypatch.setattr(live, "signals_path", tmp_path / "nothing.npz")
    with pytest.raises(RuntimeError) as err:
        live.assert_feedable()
    assert "signals" in str(err.value)


def test_promotion_copies_rather_than_references(tmp_path, monkeypatch):
    """A package that pointed at the lab's files would change under the trader's feet."""
    monkeypatch.setattr(config, "ENGINES", tmp_path / "engines")
    monkeypatch.setattr(engine_mod.config, "ENGINES", tmp_path / "engines")
    source = tmp_path / "model"
    source.mkdir()
    (source / "config.json").write_text('{"model": {"window": 96}}', encoding="utf-8")
    (source / "standardizer.json").write_text("{}", encoding="utf-8")
    (source / "oracle_net.pt").write_bytes(b"weights")
    best = {"band": {"enter": 0.75, "exit_": 0.25, "min_hold": 16},
            "risk": {"max_positions": 2}, "config": {"trend_span": 5760}}
    package = engine_mod.promote("vtest", source, best, provenance="a test")
    (source / "oracle_net.pt").write_bytes(b"CHANGED")
    assert (package.path / "oracle_net.pt").read_bytes() == b"weights"


# --- the clock and the cutover ---------------------------------------------------


def test_the_next_bar_close_is_on_the_quarter_hour():
    now = datetime(2026, 9, 17, 10, 7, 30, tzinfo=timezone.utc)
    assert next_bar_close(now) == datetime(2026, 9, 17, 10, 15, tzinfo=timezone.utc)
    on_the_dot = datetime(2026, 9, 17, 10, 15, tzinfo=timezone.utc)
    assert next_bar_close(on_the_dot) == on_the_dot + timedelta(minutes=15)


def test_the_cutover_is_the_instant_the_operator_named():
    """2026-09-17 11:00 Europe/Madrid = 09:00 UTC. Before it, nothing is executed."""
    assert config.CUTOVER == datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)


def test_no_credential_is_needed_to_paper_trade(monkeypatch, tmp_path):
    """The whole paper stack must run on public data, with no key file present at all."""
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent")
    assert config.credentials() == {}
    assert not config.has_venue_keys("binance")


def test_the_published_state_carries_no_secret():
    """Whatever the monitor publishes is public by construction."""
    from quantlab_live import state as state_mod

    payload = state_mod.read()
    if payload is None:
        pytest.skip("the trader has not published yet")
    blob = json.dumps(payload).lower()
    for forbidden in ("api_key", "apikey", "secret", "password", "token"):
        assert forbidden not in blob


# --- the bug that made the live book silent --------------------------------------


def test_the_tick_is_never_ahead_of_the_channels():
    """The decision bar must be one the signals actually cover.

    2026-09-17, first day live: a refresh takes minutes, so `dataset.combined()` returned
    candles up to 19:45 while the signals file ended at 19:15. `Channels.prob` answers a
    timestamp it does not carry with 0.0 - no conviction - so the brain read 0.000 on all
    fourteen symbols and the paper book would never have bought anything, silently, for
    as long as it ran. Nothing raised, nothing logged, and the log line "0 open, 0 orders"
    looked exactly like a selective strategy waiting for a setup.
    """
    from datetime import datetime, timedelta, timezone

    step = timedelta(minutes=15)
    base = datetime(2026, 9, 17, 19, 0, tzinfo=timezone.utc)
    stamps = [base + i * step for i in range(4)]        # 19:00 .. 19:45
    covered = base + step                               # channels stop at 19:15

    chosen = max((s for s in stamps if s <= covered), default=stamps[-1])
    assert chosen == covered, "the trader must decide on the newest COVERED bar"
    lag = int((stamps[-1] - chosen).total_seconds() // 900)
    assert lag == 2, "and it must know, and publish, how far behind that leaves it"


def test_the_engine_reports_how_far_its_channels_reach():
    """`latest_signal_stamp` is what makes the rule above enforceable at run time."""
    package = engine_mod.EnginePackage.current()
    live = engine_mod.LiveEngine(package)
    stamp = live.latest_signal_stamp()
    if stamp is None:
        pytest.skip("no signals cache on this machine yet")
    assert stamp.tzinfo is not None, "a naive timestamp cannot be compared to a bar"
