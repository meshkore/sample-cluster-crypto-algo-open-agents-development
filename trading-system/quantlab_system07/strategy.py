"""CapitulationDip — a long-only capitulation dip-buyer (system 07).

Rule, per symbol: when the causal capitulation score (system 06's feature) exceeds
`enter`, open a long; close it when EITHER a bounce target is hit, a stop is hit, or a
maximum holding horizon elapses. Portfolio-level: equal-fraction sizing, capped at
`max_positions` concurrent names, shared cash, 0.003 round-trip cost, and the same 25%
peak-to-trough mandate system 06 honours (abort to cash).

This is deliberately simple and self-contained: the edge study showed buying strong
capitulations (score>0.4) and holding ~1-2 days nets +3% to +5% at ~65% win, and the
point of system 07 is to earn in exactly the drop regimes where system 06 loses, so a
06+07 combine can raise the rolling one-year win rate without the median cost a
breadth-gated single system pays. Long-only; no shorts, no leverage, no live orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from quantlab_system06.capitulation import capitulation_score

COST = 0.003  # round-trip


@dataclass
class Trade:
    symbol: str
    entry_ts: object
    exit_ts: object
    ret: float
    reason: str


@dataclass
class CapitulationDip:
    enter: float = 0.4
    horizon: int = 96          # max bars to hold (~1 day at 15m)
    target: float = 0.06       # take-profit on the bounce
    stop: float = 0.06         # hard stop
    fraction: float = 0.20     # equity fraction per position
    max_positions: int = 4
    max_drawdown: float = 0.25
    vol_span: int = 96
    drop_span: int = 16
    keep_full_equity: bool = False   # True -> return the undecimated curve (combine studies)
    trades: list = field(default_factory=list)

    def _channels(self, bars_by_symbol):
        """Precompute the causal capitulation score + close per symbol, keyed by timestamp."""
        chan = {}
        for sym, series in bars_by_symbol.items():
            if len(series) < self.vol_span + self.drop_span + 2:
                continue
            h = np.array([b.high for b in series], float)
            l = np.array([b.low for b in series], float)
            c = np.array([b.close for b in series], float)
            v = np.array([b.volume for b in series], float)
            score = capitulation_score(h, l, c, v, vol_span=self.vol_span, drop_span=self.drop_span)
            chan[sym] = {b.timestamp: (float(c[i]), float(score[i])) for i, b in enumerate(series)}
        return chan

    def backtest(self, bars_by_symbol, *, capital: float = 100_000.0) -> dict:
        chan = self._channels(bars_by_symbol)
        if not chan:
            return {"return_pct": 0.0, "trades": 0, "equity": [], "status": "no-data"}
        timeline = sorted({ts for m in chan.values() for ts in m})
        cash = capital
        # open positions: symbol -> {qty, entry_px, entry_ts, bars_held}
        pos: dict[str, dict] = {}
        peak = capital
        equity_curve = []
        stopped = False

        def mark(ts) -> float:
            held = 0.0
            for sym, p in pos.items():
                px = chan[sym].get(ts, (p["entry_px"], 0.0))[0]
                held += p["qty"] * px
            return cash + held

        for ts in timeline:
            # exits first
            for sym in list(pos.keys()):
                if ts not in chan[sym]:
                    continue
                p = pos[sym]
                px = chan[sym][ts][0]
                p["bars_held"] += 1
                ret = px / p["entry_px"] - 1.0
                reason = None
                if ret >= self.target:
                    reason = "target"
                elif ret <= -self.stop:
                    reason = "stop"
                elif p["bars_held"] >= self.horizon:
                    reason = "horizon"
                if reason:
                    proceeds = p["qty"] * px * (1.0 - COST)
                    cash += proceeds
                    self.trades.append(Trade(sym, p["entry_ts"], ts, ret - COST, reason))
                    del pos[sym]

            equity = mark(ts)
            peak = max(peak, equity)
            if peak > 0 and equity <= peak * (1 - self.max_drawdown):
                # mandate: liquidate to cash and stop trading
                cash = equity
                pos.clear()
                stopped = True
                equity_curve.append({"timestamp": ts, "equity": equity})
                break

            # entries: strongest fresh capitulations, up to the book cap
            if len(pos) < self.max_positions:
                cands = [(sym, chan[sym][ts]) for sym in chan
                         if ts in chan[sym] and sym not in pos and chan[sym][ts][1] > self.enter]
                cands.sort(key=lambda x: x[1][1], reverse=True)
                for sym, (px, _score) in cands[: self.max_positions - len(pos)]:
                    notional = min(equity * self.fraction, cash)
                    if notional <= 0 or px <= 0:
                        continue
                    qty = notional / px
                    cash -= qty * px * (1.0 + COST)
                    pos[sym] = {"qty": qty, "entry_px": px, "entry_ts": ts, "bars_held": 0}

            equity_curve.append({"timestamp": ts, "equity": mark(ts)})

        final = equity_curve[-1]["equity"] if equity_curve else capital
        eq = np.array([e["equity"] for e in equity_curve], float)
        mdd = 0.0
        if len(eq):
            run_peak = np.maximum.accumulate(eq)
            mdd = float(np.max((run_peak - eq) / np.where(run_peak > 0, run_peak, 1.0)))
        wins = sum(1 for t in self.trades if t.ret > 0)
        return {
            "return_pct": final / capital - 1.0,
            "trades": len(self.trades),
            "win_rate": wins / len(self.trades) if self.trades else None,
            "max_drawdown": mdd,
            "status": "stopped" if stopped else "complete",
            "equity": equity_curve if self.keep_full_equity
                      else equity_curve[:: max(1, len(equity_curve) // 500)],
        }
