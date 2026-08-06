"""Per-asset regime routing (H-014).

The market detector routes every asset the same way, which is why a year
labelled BEAR from end to end puts an asset making new highs onto the bear
branch. `regime_scope="asset"` keeps the detector as a risk governor and lets
the traded series pick the mechanism.

The tests that matter here are the causality ones. A per-asset classifier is
exactly the place a lookahead hides, because the label and the price come from
the same series. Every test below has been sabotage-verified.
"""

from datetime import datetime, timedelta, timezone
import unittest

from quantlab.models import Bar
from quantlab.regime import (
    MarketContext,
    MarketRegime,
    RegimeParameters,
    RegimeTimeline,
)
from quantlab.regime_system import _RegimeRouter


def _bars(closes: list[float], start: datetime | None = None) -> list[Bar]:
    start = start or datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(days=index),
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            volume=5_000_000.0,
        )
        for index, close in enumerate(closes)
    ]


def _timeline(bars: list[Bar], regime: MarketRegime) -> RegimeTimeline:
    """A market timeline pinned to one label, so anything the router does is
    attributable to the asset scope rather than to the market detector."""
    return RegimeTimeline(
        stamps=[bar.timestamp for bar in bars],
        labels=[regime] * len(bars),
        index=[bar.close for bar in bars],
        breadth=[0.5] * len(bars),
        bar_seconds=86_400.0,
        parameters=RegimeParameters(),
    )


def _router(bars: list[Bar], market: MarketRegime, **params) -> _RegimeRouter:
    base = {
        "regime_scope": "asset",
        "asset_trend_period": 50,
        "asset_slope_period": 5,
        "asset_confirmation_bars": 3,
        # The gate is what the market label still controls; open it by default
        # so these tests isolate the routing decision.
        "bear_min_depth": 0.0,
        "bear_min_age": 0,
    }
    base.update(params)
    return _RegimeRouter(base, MarketContext(regimes=_timeline(bars, market)))


class AssetRegimeScopeTest(unittest.TestCase):
    def test_scope_must_be_recognised(self) -> None:
        with self.assertRaises(ValueError):
            _router(_bars([100.0] * 10), MarketRegime.BULL, regime_scope="planet")

    def test_a_rising_asset_is_bull_while_the_market_is_bear(self) -> None:
        """The whole point of the hypothesis, as a unit test."""
        closes = [100.0 * (1.01**index) for index in range(200)]
        bars = _bars(closes)
        router = _router(bars, MarketRegime.BEAR)
        for end in range(1, len(bars) + 1):
            router.on_bar(bars[:end])
        self.assertIs(router._asset_regime, MarketRegime.BULL)

    def test_a_falling_asset_is_bear_while_the_market_is_bull(self) -> None:
        closes = [100.0 * (0.99**index) for index in range(200)]
        bars = _bars(closes)
        router = _router(bars, MarketRegime.BULL)
        for end in range(1, len(bars) + 1):
            router.on_bar(bars[:end])
        self.assertIs(router._asset_regime, MarketRegime.BEAR)

    def test_the_label_never_uses_the_bar_it_is_trading(self) -> None:
        """Causality, asserted where it can actually be seen.

        The obvious version of this test -- swap the final bar for a crash and
        check the label held -- passes against a deliberately broken classifier,
        because hysteresis absorbs a single bar whether or not that bar was
        allowed to be read. So assert the invariant directly: after being shown
        N bars, the classifier must have consumed exactly N-1 closes.
        """
        closes = [100.0 * (1.01**index) for index in range(120)]
        bars = _bars(closes)
        router = _router(bars, MarketRegime.SIDEWAYS)
        for end in range(1, len(bars) + 1):
            router.on_bar(bars[:end])
            self.assertEqual(
                len(router._closes),
                end - 1,
                f"classifier consumed {len(router._closes)} closes from {end} bars",
            )

    def test_labels_match_when_history_is_truncated(self) -> None:
        """A prefix-equality check across many cut points: a router fed only the
        first K bars must reach the same label as one fed the whole series and
        stopped at K. Anything else means state is leaking backwards."""
        closes = []
        price = 100.0
        for cycle in range(6):
            factor = 1.02 if cycle % 2 == 0 else 0.98
            for _ in range(60):
                price *= factor
                closes.append(price)
        bars = _bars(closes)

        full = _router(bars, MarketRegime.SIDEWAYS)
        seen = []
        for end in range(1, len(bars) + 1):
            full.on_bar(bars[:end])
            seen.append(full._asset_regime)

        for cut in range(60, len(bars) + 1, 17):
            truncated = _router(bars, MarketRegime.SIDEWAYS)
            for end in range(1, cut + 1):
                truncated.on_bar(bars[:end])
            self.assertIs(
                truncated._asset_regime,
                seen[cut - 1],
                f"label disagrees when history is cut at {cut}",
            )

    def test_hysteresis_holds_a_label_through_a_single_touch(self) -> None:
        """One bar the other side of the threshold must not reroute the asset.

        The shock goes at index -2, not -1. A shock on the final bar is never
        classified at all -- the classifier stops one bar short by design -- so
        putting it there tests nothing, and this test passed against a router
        with hysteresis removed entirely until the shock was moved.
        """
        closes = [100.0 * (1.01**index) for index in range(150)]
        closes[-2] = closes[-3] * 0.5
        bars = _bars(closes)
        router = _router(bars, MarketRegime.SIDEWAYS, asset_confirmation_bars=20)
        for end in range(1, len(bars) + 1):
            router.on_bar(bars[:end])
        self.assertIs(router._asset_regime, MarketRegime.BULL)

    def test_a_regime_change_clears_every_branch(self) -> None:
        """A branch that was holding when its regime ended must not resume when
        that regime returns.

        Asserting "the signal is 0.0 on the switch bar" does not test this: at
        the moment a label confirms, the incoming branch is dormant anyway and
        returns 0.0 whether or not it was cleared. The state is what matters, so
        the state is what is asserted.
        """
        # The series has to put a branch IN a position and then take the label
        # away from it. A rise with pullbacks gets the bull branch long; the
        # sustained decline that follows moves the label out from under it.
        closes, price = [], 100.0
        for index in range(260):
            price *= 1.03 if index % 3 else 0.98
            closes.append(price)
        for _ in range(160):
            price *= 0.97
            closes.append(price)
        bars = _bars(closes)
        router = _router(bars, MarketRegime.SIDEWAYS)

        handovers = 0
        for end in range(1, len(bars) + 1):
            before = router._asset_regime
            was_holding = any(branch.active for branch in router.branches.values())
            router.on_bar(bars[:end])
            if router._asset_regime is not before:
                if was_holding:
                    handovers += 1
                self.assertFalse(
                    any(branch.active for branch in router.branches.values()),
                    f"a branch survived the handover at bar {end} still holding",
                )
        self.assertTrue(
            handovers, "no branch was ever holding at a handover, so nothing was tested"
        )

    def test_market_scope_is_untouched(self) -> None:
        """The default must route on the market label exactly as before, or
        every stored result silently changes meaning."""
        closes = [100.0 * (1.01**index) for index in range(200)]
        bars = _bars(closes)
        router = _RegimeRouter(
            {"bear_min_depth": 0.0, "bear_min_age": 0},
            MarketContext(regimes=_timeline(bars, MarketRegime.BEAR)),
        )
        self.assertEqual(router.regime_scope, "market")
        for end in range(1, len(bars) + 1):
            router.on_bar(bars[:end])
        self.assertIs(router.last_regime, MarketRegime.BEAR)

    def test_the_market_gate_still_refuses_an_early_bear(self) -> None:
        """Demoted to a risk governor, not removed: a shallow, young market bear
        must still stand the asset down however good its own trend looks.

        The series needs pullbacks. On a clean 1%-a-day rise the bull rule's RSI
        ceiling suppresses every signal on its own, so "no signals while gated"
        is true whether or not the gate exists -- which is how an earlier version
        of this test passed against a router with the gate deleted. The open-gate
        half is what makes the closed-gate half mean anything.
        """
        closes, price = [], 100.0
        for index in range(220):
            price *= 1.03 if index % 3 else 0.98
            closes.append(price)
        bars = _bars(closes)

        gated = _router(bars, MarketRegime.BEAR, bear_min_depth=0.70, bear_min_age=240)
        blocked = [gated.on_bar(bars[:end]) for end in range(1, len(bars) + 1)]

        allowed = _router(bars, MarketRegime.BEAR)
        traded = [allowed.on_bar(bars[:end]) for end in range(1, len(bars) + 1)]

        self.assertTrue(
            any(signal > 0 for signal in traded),
            "the control never traded, so the gated run proves nothing",
        )
        self.assertEqual(set(blocked), {0.0})
        # The classifier kept running underneath the gate, so nothing resumes on
        # a stale label when the environment qualifies again.
        self.assertIs(gated._asset_regime, MarketRegime.BULL)


if __name__ == "__main__":
    unittest.main()
