"""Simulated fills at the REAL spread, with the laboratory's own impact model on top.

Operator, 2026-09-17: *"ideally a simulation of where the order goes in, that computes
the real slippage using the real-time spreads of Binance."*

So this broker invents nothing about price. It takes the top of the book as the venue
publishes it at the moment of the decision, pays the ask to buy and receives the bid to
sell, and then charges the same two costs the backtest charges:

* **commission**, a flat 10 bps, Binance spot's taker fee;
* **market impact**, `IMPACT_BPS * sqrt(participation)` where participation is the order
  as a share of the last candle's traded value - the size-dependent cost the operator
  asked for on 2026-09-02 ("our own volume would alter the figures"), calibrated on this
  universe's own candles and worth 60 bps for an order the size of a whole bar.

What it does NOT charge is the backtest's flat 5 bps slippage: that number was a stand-in
for the spread, and here the spread is measured. Every fill records the mid at decision
time and the realised slippage in bps against it, so the assumption the research was
built on can be audited against what the market actually offered, day after day.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from ..book import Fill
from ..feed import Quote

COMMISSION_BPS = 10.0      # Binance spot taker
IMPACT_BPS = 60.0          # the lab's calibrated square-root impact (launch.IMPACT_BPS)


class PaperBroker:
    """Fills computed from the live book. Moves no money anywhere."""

    name = "paper"
    live_money = False

    def __init__(self, commission_bps: float = COMMISSION_BPS,
                 impact_bps: float = IMPACT_BPS):
        self.commission_bps = float(commission_bps)
        self.impact_bps = float(impact_bps)

    # -- cost model ------------------------------------------------------------

    def _impact(self, notional: float, bar_value: float | None) -> float:
        """Extra bps paid for being big relative to the traded volume of one candle."""
        if not bar_value or bar_value <= 0 or notional <= 0:
            return 0.0
        participation = min(1.0, notional / bar_value)
        return self.impact_bps * math.sqrt(participation)

    # -- orders ----------------------------------------------------------------

    def buy(self, symbol: str, notional: float, quote: Quote, reason: str = "",
            bar_value: float | None = None) -> Fill:
        impact_bps = self._impact(notional, bar_value)
        price = quote.ask * (1.0 + impact_bps / 10_000.0)
        quantity = notional / price if price > 0 else 0.0
        fee = notional * self.commission_bps / 10_000.0
        return Fill(at=datetime.now(timezone.utc), symbol=symbol, side="BUY",
                    quantity=quantity, price=price, notional=quantity * price, fee=fee,
                    reason=reason, mid_at_decision=quote.mid,
                    slippage_bps=10_000.0 * (price - quote.mid) / quote.mid if quote.mid else None)

    def sell(self, symbol: str, quantity: float, quote: Quote, reason: str = "",
             bar_value: float | None = None) -> Fill:
        rough = quantity * quote.bid
        impact_bps = self._impact(rough, bar_value)
        price = quote.bid * (1.0 - impact_bps / 10_000.0)
        notional = quantity * price
        fee = notional * self.commission_bps / 10_000.0
        return Fill(at=datetime.now(timezone.utc), symbol=symbol, side="SELL",
                    quantity=quantity, price=price, notional=notional, fee=fee,
                    reason=reason, mid_at_decision=quote.mid,
                    slippage_bps=10_000.0 * (quote.mid - price) / quote.mid if quote.mid else None)
