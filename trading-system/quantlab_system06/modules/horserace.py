"""Horse-race: lean into the laggards when the pack is already running.

Idea `lead-lag-cascade` (operator, 2026-08-25). A rally does not lift every coin at
once: some fire first, then BTC takes a leading role, then the laggards catch up. So
when a large fraction of the universe is already in a strong up-move AND the leader
(BTC) is up, the coins that have NOT yet moved are the ones most likely to run next.
This module reads that cross-sectional state from the existing per-symbol momentum
channel (the same way `regime` reads breadth) and UPSIZES the laggards the oracle is
entering, to lean into the expected catch-up — capturing rotation alpha the per-symbol
oracle cannot see.

Safe by construction: it only scales the size of names the rest of the stack already
chose to enter (a size multiplier, composed by product) — it never forces an entry on
its own and never vetoes, so it can only tilt capital toward laggards during a
confirmed pack rally. Off (`horserace <= 0`) -> the module abstains entirely.

The stronger, standalone-voter version (enter laggards the oracle misses) is tracked
as A33 (multi-discipline committee), which needs the vote/enter architecture change.
"""

from __future__ import annotations

from statistics import median

from .base import MarketView, ModuleOutput

LEADER = "BTCUSDT"
MIN_NAMES = 5          # need a real cross-section before judging the pack
HOT_FRACTION = 0.5     # "pack is running" = at least half the universe with positive momentum
MAX_BOOST = 0.30       # deepest laggard upsize (size x1.3) at full strength


class HorseRace:
    def __init__(self, horserace: float = 0.0):
        self.name = "horserace"
        self.weight = 0.0  # sizes only; never votes direction, never vetoes
        self.strength = float(horserace)

    def reset(self) -> None:
        pass

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.strength <= 0:
            return out
        ch, ns = view.channels, view.ns
        moms = {s: ch.momentum(s, ns) for s in view.candles}
        moms = {s: m for s, m in moms.items() if m is not None}
        if len(moms) < MIN_NAMES:
            return out
        vals = list(moms.values())
        pack_med = median(vals)
        hot_frac = sum(1 for m in vals if m > 0) / len(vals)
        leader = moms.get(LEADER)
        pack_running = hot_frac >= HOT_FRACTION and (leader is None or leader > 0)
        if not pack_running:
            return out
        boosted = 0
        for symbol, m in moms.items():
            if m < pack_med:  # a laggard while the pack runs -> lean in for the catch-up
                out.vote(symbol, size_mult=1.0 + self.strength * MAX_BOOST)
                boosted += 1
        if boosted:
            out.note = f"horserace: pack running ({hot_frac:.0%}), upsized {boosted} laggard(s)"
        return out
