"""Which assets may be bought on THIS bar, decided on this bar's own evidence.

A trading system that runs on an exchange can only buy what is listed and liquid
at the moment it decides. That set is not a list someone writes down once: coins
list, coins die, and a name that carried $400M a day in 2021 can carry $60k a day
in 2026 while still being quoted. Any universe fixed in advance is either a
fiction about the past or a bet on the future.

So this decides membership per bar, from the same tick the brain is reading:

    gate = LiquidityGate(minimum_turnover=10_000_000, maximum_assets=100)
    allowed = gate.tradeable(tick["indicators"])

`dollar_volume_20` is the trailing twenty-bar mean of close x volume, already
one of the served columns, and like every other column it is a function of bars
up to its own. Membership is therefore causal by construction: the value read on
bar t was knowable on bar t, and the order it permits fills at the open of t+1.
There is no rebalancing schedule to keep, no membership file to maintain, and no
date on which someone has to remember to re-rank.

**Two asymmetries that are deliberate.**

Buying is gated and selling never is. A position in an asset whose turnover has
collapsed is exactly the position you most want to be able to close; gating the
exit would strand it for ever and call the resulting equity a result. The gate
answers "what may I enter", and nothing else.

An asset with no turnover value yet -- inside its first twenty bars -- is not
tradeable. Absence of evidence is not evidence of liquidity, and a freshly
listed coin on its third day is the single most expensive thing this laboratory
could buy.

**What this does not fix.** We only hold candles for symbols that are listed
today, so an asset that was liquid in 2021 and delisted in 2023 is absent from
the data entirely and cannot be admitted by any rule written here. That is
survivorship bias in the DATA, upstream of this file, and it flatters every
pre-2026 number. `universes.py` in the orchestrator states it at the point of
selection; this note exists so nobody reads a per-bar membership rule as a claim
to have solved it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The trailing dollar-turnover column every gate reads. Twenty bars rather than
# fifty: the shorter window notices a collapse in liquidity while there is still
# time to stop buying into it.
TURNOVER_KEY = "dollar_volume_20"


@dataclass(frozen=True)
class LiquidityGate:
    """The tradeable set, recomputed every bar.

    `minimum_turnover` is in quote currency per bar and is the real constraint:
    it is what makes a fill plausible at all. `maximum_assets` is a cap on top
    of it, expressing "we will not run a book wider than this" -- it binds only
    when more names clear the floor than we are willing to hold. Measured on our
    own data at a $10M floor, the count that clears ranges from 3 in early 2018
    to 134 in early 2025, so the floor does most of the work and the cap is a
    guard rail rather than a selection rule.

    Zero disables either constraint, which makes an ungated gate expressible and
    keeps the default harmless.
    """

    minimum_turnover: float = 0.0
    maximum_assets: int = 0
    turnover_key: str = TURNOVER_KEY

    def turnover(self, row: dict[str, Any] | None) -> float | None:
        """This bar's trailing turnover, or None if it is not yet knowable."""
        if not row:
            return None
        value = row.get(self.turnover_key)
        if value is None:
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        # NaN fails every comparison silently, which is how an unranked asset
        # would otherwise slip into the top of a sorted list.
        return value if value == value and value >= 0 else None

    def tradeable(self, indicators: dict[str, dict[str, Any]]) -> frozenset[str]:
        """Which symbols may be BOUGHT on this bar. Sells are never gated."""
        ranked: list[tuple[float, str]] = []
        for symbol, row in (indicators or {}).items():
            value = self.turnover(row)
            if value is None or value < self.minimum_turnover:
                continue
            ranked.append((value, symbol))
        # Turnover descending, then symbol ascending, so a tie resolves the same
        # way on every machine and a run stays reproducible by a stranger.
        ranked.sort(key=lambda pair: (-pair[0], pair[1]))
        if self.maximum_assets > 0:
            ranked = ranked[: self.maximum_assets]
        return frozenset(symbol for _, symbol in ranked)

    @property
    def enabled(self) -> bool:
        return self.minimum_turnover > 0 or self.maximum_assets > 0

    def describe(self) -> dict[str, Any]:
        """What a recorded run should carry about the scope it was run at.

        A return is meaningless without the universe that produced it, and the
        universe here is a rule rather than a list -- so the rule is what gets
        stored.
        """
        return {
            "rule": "per-bar trailing turnover",
            "turnover_key": self.turnover_key,
            "minimum_turnover": self.minimum_turnover,
            "maximum_assets": self.maximum_assets,
        }
