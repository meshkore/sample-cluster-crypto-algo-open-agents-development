"""What a venue has to be able to do, and nothing more.

The trader talks to this protocol only. A paper broker and a real one differ in exactly
one respect - whether the fill is computed or reported - and everything above this line
is written once.
"""

from __future__ import annotations

from typing import Protocol

from ..book import Fill
from ..feed import Quote


class Broker(Protocol):
    """Places market orders and reports what happened."""

    name: str
    live_money: bool

    def buy(self, symbol: str, notional: float, quote: Quote, reason: str = "",
            bar_value: float | None = None) -> Fill:
        """Spend `notional` of cash on `symbol`. Returns the fill actually obtained."""

    def sell(self, symbol: str, quantity: float, quote: Quote, reason: str = "",
             bar_value: float | None = None) -> Fill:
        """Sell `quantity` of `symbol`. Returns the fill actually obtained."""
