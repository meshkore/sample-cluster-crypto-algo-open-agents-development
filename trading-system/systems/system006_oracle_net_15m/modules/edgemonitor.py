"""The circuit breaker: stand down when our OWN edge stops working.

Idea A39, forced by the two findings that dominate this system's research:

  - Two independent disciplines (the oracle TCN and a gradient-boosted tree on
    candlestick + probabilistic features) both hold a stable edge for six research
    years and then INVERT in the sealed window, in every fractal-regime bucket. So the
    change is not visible in any market indicator we have.
  - Refitting on recent history does NOT track it: rolling 1y/2y training windows score
    roughly a third of the expanding window's edge on the same research years (A38,
    refuted). The edge is slow to estimate and cannot be re-learned quickly.

If a regime change is neither predictable from the market nor learnable by refitting,
the only honest defence left is to watch the strategy's own results and withdraw when
they deteriorate. That is what this module does: it keeps a rolling record of the
realized return of every position the book has CLOSED, and when that expectancy falls
below zero it scales the book's deployment down toward `floor`, restoring full size as
soon as the trades work again.

It is deliberately self-referential and causal — it reads only outcomes that have
already happened — and it never votes on direction or vetoes a name; it only turns the
whole book's exposure down. Off (`edge_monitor <= 0`) -> abstains entirely.

This cannot create edge. It is insurance: it converts "a year of break-even churn while
the edge is inverted" into "a small loss and a smaller book", which is exactly the
failure the sealed window exposed.
"""

from __future__ import annotations

from collections import deque

from .base import MarketView, ModuleOutput


class EdgeMonitor:
    def __init__(self, edge_monitor: float = 0.0, window: int = 40,
                 floor: float = 0.25, min_trades: int = 15):
        self.name = "edgemonitor"
        self.weight = 0.0  # never votes direction; only scales deployment
        self.strength = float(edge_monitor)
        self.window = int(window)
        self.floor = float(floor)
        self.min_trades = int(min_trades)
        self._outcomes: deque = deque(maxlen=self.window)
        self._open: dict[str, float] = {}   # symbol -> last seen unrealized return

    def reset(self) -> None:
        self._outcomes = deque(maxlen=self.window)
        self._open = {}

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.strength <= 0:
            return out
        positions = view.account.get("positions") or {}

        # Anything we were holding that is gone this bar has been CLOSED: bank its last
        # known return as a realized outcome. (The exact fill differs by a bar; this is a
        # monitor, not an accountant, and it never feeds a price back into the book.)
        for symbol, last in list(self._open.items()):
            if symbol not in positions:
                self._outcomes.append(last)
                del self._open[symbol]

        # Refresh the running return of everything still held.
        for symbol, holding in positions.items():
            unreal = holding.get("unrealized_pct")
            if unreal is None:
                entry = holding.get("entry_price")
                price = view.price(symbol)
                unreal = (price / float(entry) - 1.0) if entry and price else None
            if unreal is not None:
                self._open[symbol] = float(unreal)

        if len(self._outcomes) < self.min_trades:
            return out                      # not enough evidence yet — stay out of the way

        expectancy = sum(self._outcomes) / len(self._outcomes)
        if expectancy >= 0:
            return out                      # the edge is working; no opinion

        # Losing on average over the last `window` closed trades: scale the book down in
        # proportion to how badly, bounded by `floor` so it never goes fully to cash on
        # a wobble. A 1% average loss per trade at full strength reaches the floor.
        severity = min(1.0, abs(expectancy) / 0.01)
        mult = 1.0 - self.strength * severity * (1.0 - self.floor)
        out.deploy_mult = max(self.floor, mult)
        out.note = (f"edge monitor: last {len(self._outcomes)} trades average "
                    f"{expectancy * 100:+.2f}% -> deploy x{out.deploy_mult:.2f}")
        return out
