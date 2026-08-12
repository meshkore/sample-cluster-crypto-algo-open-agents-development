from __future__ import annotations

from collections import deque

from quantlab_trading.brains import register
from quantlab_trading.runner import Decision
from quantlab_intraday.moneymanagement import intraday_money_management


class _SlidingExtreme:
    """Amortised O(1) sliding-window max or min over a stream of scalars.

    Query .value() BEFORE pushing the current bar so the extreme reflects the
    prior `window` closed bars only -- this is what keeps the breakout test
    strictly backward-looking (no peeking at the bar we are deciding on).
    """

    def __init__(self, window: int, want_max: bool) -> None:
        self.window = int(window)
        self.want_max = bool(want_max)
        self._dq: deque = deque()  # (index, value), monotone
        self._i = -1

    def push(self, value: float) -> None:
        self._i += 1
        if self.want_max:
            while self._dq and self._dq[-1][1] <= value:
                self._dq.pop()
        else:
            while self._dq and self._dq[-1][1] >= value:
                self._dq.pop()
        self._dq.append((self._i, value))
        cutoff = self._i - self.window
        while self._dq and self._dq[0][0] <= cutoff:
            self._dq.popleft()

    def value(self):
        return self._dq[0][1] if self._dq else None


class _SymbolState:
    def __init__(self, entry_bars: int, exit_bars: int) -> None:
        self.n = 0
        self.prev_close = None
        self.ema_slow = None
        self.ema_vol = None
        self.atr = None
        self.entry_hi = _SlidingExtreme(entry_bars, want_max=True)
        self.exit_lo = _SlidingExtreme(exit_bars, want_max=False)
        # populated while a position is open
        self.peak_close = None
        self.entry_atr = None


@register(
    "donchian-trend-crypto",
    "20/10-day Donchian breakout, long-term trend gate, ATR-trailing exit, vol-targeted sizing",
)
class DonchianTrendBrain:
    """Long-only time-series-momentum / Turtle-style breakout on 5-minute crypto.

    Enter a new N-day high only while price is above its long trend and the
    breakout bar carries above-average volume. Ride the move with an ATR
    trailing stop, cut it if price loses the shorter Donchian floor. Positions
    are sized so one stop-out risks a fixed slice of equity, so the book holds
    its winners and bleeds the fixed 0.30% round-trip cost only on the rare,
    positively-skewed entries that trend-following is built to catch.
    """

    def __init__(self, **params):
        self.params = dict(params)

        def f(name, default):
            v = float(params.get(name, default))
            self.params[name] = v
            return v

        def i(name, default):
            v = int(params.get(name, default))
            self.params[name] = v
            return v

        self.maximum_drawdown = f("maximum_drawdown", 0.25)
        self.maximum_position_fraction = f("maximum_position_fraction", 0.25)

        # REQUIRED: the harness serialises this and reads maximum_drawdown from it.
        self.policy = intraday_money_management(
            maximum_drawdown=self.maximum_drawdown,
            maximum_position_fraction=self.maximum_position_fraction,
        )

        self.bars_per_day = i("bars_per_day", 288)  # 5-minute bars
        self.entry_bars = int(f("entry_days", 20.0) * self.bars_per_day)
        self.exit_bars = int(f("exit_days", 10.0) * self.bars_per_day)
        self.trend_slow_bars = int(f("trend_slow_days", 50.0) * self.bars_per_day)
        self.atr_bars = int(f("atr_days", 1.0) * self.bars_per_day)
        self.vol_bars = int(f("vol_days", 1.0) * self.bars_per_day)
        self.atr_trail_mult = f("atr_trail_mult", 5.0)
        self.risk_fraction = f("risk_fraction", 0.0075)
        self.volume_mult = f("volume_mult", 1.2)
        self.max_concurrent = i("max_concurrent", 3)
        self.min_notional_frac = f("min_notional_frac", 0.01)

        self._slow_alpha = 2.0 / (self.trend_slow_bars + 1.0)
        self._vol_alpha = 2.0 / (self.vol_bars + 1.0)

        self._warmup = max(self.entry_bars, self.trend_slow_bars) + 1

        self.state: dict = {}
        self.peak_equity = None

        self.bars_seen = 0
        self.entries = 0

    # ------------------------------------------------------------------
    def _st(self, symbol: str) -> _SymbolState:
        s = self.state.get(symbol)
        if s is None:
            s = _SymbolState(self.entry_bars, self.exit_bars)
            self.state[symbol] = s
        return s

    def _update(self, s: _SymbolState, o, h, l, c, v) -> None:
        s.n += 1
        # Wilder ATR
        if s.prev_close is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - s.prev_close), abs(l - s.prev_close))
        if s.atr is None:
            s.atr = tr
        else:
            s.atr += (tr - s.atr) / self.atr_bars
        # long-trend EMA of close
        if s.ema_slow is None:
            s.ema_slow = c
        else:
            s.ema_slow += self._slow_alpha * (c - s.ema_slow)
        # volume EMA
        if s.ema_vol is None:
            s.ema_vol = v
        else:
            s.ema_vol += self._vol_alpha * (v - s.ema_vol)
        s.prev_close = c

    # ------------------------------------------------------------------
    def decide(self, tick: dict) -> Decision:
        self.bars_seen += 1
        decision = Decision()

        account = tick.get("account", {}) or {}
        equity = float(account.get("equity", 0.0) or 0.0)
        cash = float(account.get("cash", 0.0) or 0.0)
        positions = account.get("positions", {}) or {}

        # Drawdown mandate -- checked first, ends the run.
        if equity > 0.0:
            if self.peak_equity is None or equity > self.peak_equity:
                self.peak_equity = equity
            if self.peak_equity and equity <= self.peak_equity * (1.0 - self.maximum_drawdown):
                decision.note = "drawdown mandate reached; flattening and stopping"
                for sym, p in positions.items():
                    if float(p.get("quantity", 0.0) or 0.0) > 0.0:
                        decision.sell(sym, reason="drawdown-mandate")
                decision.stop = (
                    "drawdown mandate: equity %.0f is %.2f%% below peak %.0f"
                    % (equity, 100.0 * (1.0 - equity / self.peak_equity), self.peak_equity)
                )
                return decision

        candles = tick.get("candles", {}) or {}

        held = 0
        for sym, p in positions.items():
            if float(p.get("quantity", 0.0) or 0.0) > 0.0:
                held += 1
        opened_this_bar = 0

        notes = []

        for symbol in sorted(candles.keys()):
            bar = candles[symbol]
            try:
                o = float(bar["open"]); h = float(bar["high"])
                l = float(bar["low"]); c = float(bar["close"])
                v = float(bar["volume"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (c > 0.0) or not (h >= l):
                continue

            s = self._st(symbol)

            # read strictly-prior extremes before folding this bar in
            prior_hi = s.entry_hi.value()
            prior_lo = s.exit_lo.value()

            pos = positions.get(symbol) or {}
            qty = float(pos.get("quantity", 0.0) or 0.0)
            in_pos = qty > 0.0

            if in_pos:
                if s.peak_close is None:
                    s.peak_close = c
                    s.entry_atr = s.atr if s.atr else (h - l)
                if c > s.peak_close:
                    s.peak_close = c
                atr = s.atr if s.atr else s.entry_atr
                trail = s.peak_close - self.atr_trail_mult * (atr or 0.0)
                exit_floor = prior_lo
                stop_hit = c <= trail
                floor_hit = exit_floor is not None and c < exit_floor
                if stop_hit or floor_hit:
                    reason = "atr-trail" if stop_hit else "donchian-exit"
                    decision.sell(symbol, reason=reason,
                                  rationale="close %.4f vs trail %.4f floor %s"
                                  % (c, trail, ("%.4f" % exit_floor) if exit_floor is not None else "na"))
                    s.peak_close = None
                    s.entry_atr = None
                    held -= 1
            else:
                s.peak_close = None
                s.entry_atr = None
                ready = s.n >= self._warmup and prior_hi is not None
                trend_ok = s.ema_slow is not None and c > s.ema_slow
                breakout = ready and c > prior_hi
                vol_ok = s.ema_vol is not None and v >= self.volume_mult * s.ema_vol
                room = (held + opened_this_bar) < self.max_concurrent
                atr = s.atr or 0.0
                if breakout and trend_ok and vol_ok and room and atr > 0.0 and equity > 0.0:
                    stop_dist = self.atr_trail_mult * atr
                    if stop_dist > 0.0:
                        risk_amt = self.risk_fraction * equity
                        notional = risk_amt * c / stop_dist
                        cap = self.maximum_position_fraction * equity
                        notional = min(notional, cap, max(0.0, cash * 0.98))
                        if notional >= self.min_notional_frac * equity:
                            decision.buy(
                                symbol, notional,
                                reason="donchian-breakout",
                                rationale="close %.4f > %d-bar high %.4f, above trend %.4f, vol x%.2f"
                                % (c, self.entry_bars, prior_hi, s.ema_slow,
                                   (v / s.ema_vol) if s.ema_vol else 0.0),
                            )
                            self.entries += 1
                            opened_this_bar += 1

            # fold current bar into rolling state AFTER using the prior view
            self._update(s, o, h, l, c, v)
            s.entry_hi.push(h)
            s.exit_lo.push(l)

            if len(notes) < 4:
                notes.append("%s c=%.4f" % (symbol, c))

        decision.note = ("held=%d opened=%d | " % (held, opened_this_bar)) + ", ".join(notes)
        return decision

    # ------------------------------------------------------------------
    def parameters(self) -> dict:
        return {k: v for k, v in self.params.items()
                if isinstance(v, (int, float, str, bool, type(None)))}

    def diagnostics(self) -> dict:
        return {"bars_seen": self.bars_seen, "entries": self.entries}