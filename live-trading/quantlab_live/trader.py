"""The loop: wait for a candle, ask the brain, execute, publish. Forever.

    python -m quantlab_live.trader              # paper, from the cutover onwards
    python -m quantlab_live.trader --once       # one bar and exit (what the tests drive)
    python -m quantlab_live.trader --dry-run    # decide and publish, execute nothing

The shape is the one `quantlab_core.runner` documents for the backtest, with the clock
turned the other way round: there, the loop pulls ticks as fast as the CPU allows; here,
the market produces one every fifteen minutes and the loop waits.

    while True:
        bar    = feed.wait_for_close()
        tick   = {timestamp, candles, account}
        orders = brain.decide(tick).orders
        fills  = [broker.execute(o) for o in orders]
        book.apply(fills); publish()

Everything that could make this differ from the tested system is either refused or
recorded: the engine refuses to run with a lever it cannot feed, the trader refuses to
trade before the cutover instant, and every fill stores the mid it was decided against so
the modelled cost can be audited against the real one.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from . import config, state as publish
from .book import Fill, LiveBook, append_ledger
from .brokers.paper import PaperBroker
from .engine import EnginePackage, LiveEngine
from .feed import BinanceFeed

STOP_FILE = config.STATE_DIR / "STOP"
OVERLAY_EVERY_BARS = 4          # hourly, unless a live candidate forces it sooner
SETTLE_SECONDS = 20             # let the venue finish the candle before asking for it


def log(message: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}  {message}"
    print(line, flush=True)
    try:
        config.ensure_state_dir()
        with config.LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def next_bar_close(now: datetime | None = None) -> datetime:
    """The instant the candle currently forming will close."""
    now = now or datetime.now(timezone.utc)
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(
        (epoch // config.BAR_SECONDS + 1) * config.BAR_SECONDS, tz=timezone.utc)


class Trader:
    def __init__(self, dry_run: bool = False, broker=None, feed=None):
        config.ensure_state_dir()
        self.symbols = config.universe()
        self.feed = feed or BinanceFeed(interval=config.INTERVAL)
        self.broker = broker or PaperBroker()
        self.book = LiveBook.load()
        self.dry_run = dry_run
        self.package = EnginePackage.current()
        self.engine = LiveEngine(self.package, symbols=self.symbols)
        self.brain = None
        self.bars_seen = 0
        self.last_overlay_bar = -999
        self.halted: str | None = None
        self.decision_lag_bars = 0

    # -- engine lifecycle ------------------------------------------------------

    def start(self) -> None:
        log(f"engine {self.package.version} | {len(self.symbols)} symbols | "
            f"broker {self.broker.name} ({'PAPER' if not self.broker.live_money else 'LIVE MONEY'})")
        self.engine.refresh_signals()
        self.engine.refresh_overlays()
        self.brain = self.engine.build_brain()
        self.last_overlay_bar = self.bars_seen

    def check_engine_swap(self) -> bool:
        """Between bars, never inside a decision. The book is not touched by a swap."""
        pointer = EnginePackage.current()
        if pointer.version == self.package.version:
            return False
        old = self.package.version
        log(f"ENGINE SWAP {old} -> {pointer.version}")
        self.package = pointer
        self.engine = LiveEngine(self.package, symbols=self.symbols)
        self.engine.refresh_signals()
        self.engine.refresh_overlays()
        self.brain = self.engine.build_brain()
        append_ledger({"at": datetime.now(timezone.utc).isoformat(), "kind": "ENGINE_SWAP",
                       "from": old, "to": pointer.version,
                       "equity": self.book.equity, "positions": list(self.book.positions),
                       "why": json.loads(config.CURRENT_ENGINE.read_text(encoding="utf-8")).get("why")})
        return True

    # -- one bar ---------------------------------------------------------------

    def _bars_and_tick(self) -> tuple[dict[str, list], dict[str, Any]] | None:
        """The candles every channel was computed on, and the tick built from them."""
        from system006_oracle_net_15m.dataset import Dataset  # noqa: PLC0415

        dataset = Dataset(data_root=self.engine.data_root, symbols=self.symbols,
                          interval=config.INTERVAL)
        bars = dataset.combined()
        stamps = sorted({b.timestamp for series in bars.values() for b in series})
        if not stamps:
            return None
        # Decide on the newest bar the CHANNELS cover, not the newest bar the venue has
        # closed. They differ by however long the refresh took, and asking the channels
        # for a bar they do not carry returns 0.0 conviction on every symbol - a live
        # book that silently never trades. The fill still happens at the current price.
        covered = self.engine.latest_signal_stamp()
        latest = max((s for s in stamps if covered is None or s <= covered),
                     default=stamps[-1])
        self.decision_lag_bars = int((stamps[-1] - latest).total_seconds()
                                     // config.BAR_SECONDS)
        if self.decision_lag_bars > 2:
            log(f"  channels are {self.decision_lag_bars} bars behind the market "
                f"(deciding on {latest.isoformat()})")
        # The bar AT the decision timestamp, not the newest bar of each series. Those are
        # the same thing only when the channels are level with the market; the moment the
        # refresh falls a bar behind, `series[-1].timestamp == latest` is false for every
        # symbol, the tick carries NO candles, and the brain politely decides nothing.
        # That is how the book stayed empty through a bar on which it wanted to buy two
        # names - the same silent-zero failure as the timestamp bug, one layer down.
        candles = {}
        for symbol, series in bars.items():
            bar = next((b for b in reversed(series[-8:]) if b.timestamp == latest), None)
            if bar is not None:
                candles[symbol] = {"open": bar.open, "high": bar.high, "low": bar.low,
                                   "close": bar.close, "volume": bar.volume}
        if len(candles) < max(2, len(self.symbols) // 2):
            log(f"  only {len(candles)}/{len(self.symbols)} symbols have a candle at "
                f"{latest.isoformat()} - deciding on a partial universe")
        tick = {"timestamp": latest.isoformat(), "candles": candles,
                "account": self.book.account_payload(), "done": False,
                "status": "running", "sequence": self.bars_seen}
        return bars, tick

    def _execute(self, orders: list[dict[str, Any]], bars: dict[str, list]) -> list[Fill]:
        quotes = self.feed.quotes(self.symbols)
        self.book.mark({s: q.mid for s, q in quotes.items()})
        fills: list[Fill] = []
        for order in orders:
            symbol = order["symbol"]
            quote = quotes.get(symbol)
            if quote is None:
                log(f"  SKIP {symbol}: no book")
                continue
            series = bars.get(symbol) or []
            bar_value = (series[-1].volume * series[-1].close) if series else None
            try:
                if order["side"] == "BUY":
                    notional = min(float(order.get("notional") or 0.0), self.book.cash)
                    if notional <= 0:
                        continue
                    fill = self.broker.buy(symbol, notional, quote,
                                           reason=order.get("reason", ""), bar_value=bar_value)
                else:
                    held = self.book.positions.get(symbol)
                    if not held:
                        continue
                    fill = self.broker.sell(symbol, held.quantity, quote,
                                            reason=order.get("reason", ""), bar_value=bar_value)
                fill.engine = self.package.version
                if self.dry_run:
                    log(f"  DRY {fill.side} {symbol} {fill.notional:,.2f} @ {fill.price:,.6f}")
                    continue
                self.book.apply_fill(fill)
                append_ledger({"kind": "FILL", **fill.to_json()})
                fills.append(fill)
                log(f"  {fill.side} {symbol} {fill.notional:,.2f} @ {fill.price:,.6f} "
                    f"(slip {fill.slippage_bps:.1f} bps, fee {fill.fee:.2f})"
                    + (f" realised {fill.realised:+,.2f}" if fill.realised is not None else ""))
            except ValueError as exc:
                log(f"  REJECTED {order['side']} {symbol}: {exc}")
        return fills

    def step(self) -> dict[str, Any]:
        """One bar: refresh, decide, execute, publish. Returns what was published."""
        self.check_engine_swap()
        # Half a bar: fresh enough to hold the newest candle, old enough that a startup
        # refresh followed immediately by the first bar does not export twice.
        self.engine.refresh_signals(min_age_seconds=config.BAR_SECONDS / 2)

        loaded = self._bars_and_tick()
        if loaded is None:
            raise RuntimeError("no candles: the catalogue returned nothing")
        bars, tick = loaded
        self.bars_seen += 1

        # The overlays run on a slower clock because they cost minutes, EXCEPT when the
        # bar we are about to decide on is itself an entry candidate: there, a missing
        # meta verdict would make the filter abstain and the live system would take a
        # trade the tested system would have declined.
        due = (self.bars_seen - self.last_overlay_bar) >= OVERLAY_EVERY_BARS
        if due or self._is_candidate(tick):
            self.engine.refresh_overlays(bars=bars)
            self.last_overlay_bar = self.bars_seen
        self.engine.reload_channels(self.brain)

        quotes = self.feed.quotes(self.symbols)
        self.book.mark({s: q.mid for s, q in quotes.items()})
        tick["account"] = self.book.account_payload()

        decision = self.brain.decide(tick)
        fills: list[Fill] = []
        if decision.stop:
            self.halted = decision.stop
            log(f"BRAIN STOP: {decision.stop}")
            append_ledger({"at": datetime.now(timezone.utc).isoformat(), "kind": "STOP",
                           "reason": decision.stop, "equity": self.book.equity})
        elif datetime.now(timezone.utc) < config.CUTOVER:
            log(f"before the cutover ({config.CUTOVER.isoformat()}): "
                f"{len(decision.orders)} order(s) withheld")
        else:
            fills = self._execute(decision.orders, bars)

        self.book.save()
        self.engine.save_soft_state(self.brain)
        published = publish.publish(book=self.book, package=self.package, tick=tick,
                                    decision=decision, fills=fills, quotes=quotes,
                                    halted=self.halted, dry_run=self.dry_run,
                                    overlays_at=self.engine._overlays_at,
                                    signals_at=self.engine._refreshed_at)
        log(f"bar {tick['timestamp']} (lag {self.decision_lag_bars}) | "
            f"equity {self.book.equity:,.2f} "
            f"({self.book.return_pct:+.2%}) | dd {self.book.drawdown:.2%} | "
            f"{len(self.book.positions)} open | {len(decision.orders)} order(s) | "
            f"{decision.note[:70]}")
        return published

    def _is_candidate(self, tick: dict[str, Any]) -> bool:
        """Would this bar open a position on the primary rule alone?"""
        try:
            from system006_oracle_net_15m.orchestrator import _ns  # noqa: PLC0415

            channels = self.brain._brain._channels
            ns = _ns(tick["timestamp"])
            enter = float(self.package.band["enter"])
            for symbol in tick.get("candles", {}):
                if channels.prob(symbol, ns) >= enter and channels.uptrend(symbol, ns):
                    return True
        except Exception:  # noqa: BLE001 - a probe, never a reason to stop trading
            return True
        return False

    # -- the loop --------------------------------------------------------------

    def run(self, once: bool = False) -> int:
        self.start()
        while True:
            if STOP_FILE.exists():
                log("STOP file present; standing down (positions are left as they are)")
                return 0
            try:
                self.step()
            except Exception as exc:  # noqa: BLE001
                log(f"ERROR {type(exc).__name__}: {exc}")
                append_ledger({"at": datetime.now(timezone.utc).isoformat(), "kind": "ERROR",
                               "error": f"{type(exc).__name__}: {exc}"})
                if once:
                    raise
            if once:
                return 0
            target = next_bar_close() + timedelta(seconds=SETTLE_SECONDS)
            wait = max(5.0, (target - datetime.now(timezone.utc)).total_seconds())
            time.sleep(wait)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="one bar, then exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="decide and publish, but execute nothing")
    parser.add_argument("--venue", default="paper",
                        help="paper (default). A venue that can move real money needs "
                             "keys outside the repo AND an explicit confirmation.")
    args = parser.parse_args(argv)
    if args.venue != "paper":
        print("Only the paper broker is wired. A venue broker that can move real money "
              "is deliberately not reachable from a flag.", file=sys.stderr)
        return 2
    return Trader(dry_run=args.dry_run).run(once=args.once)


if __name__ == "__main__":
    sys.exit(main())
