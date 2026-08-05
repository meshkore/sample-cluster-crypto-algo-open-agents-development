"""The time stop (H-012).

H-011 found that the exit, not the entry, is what loses money: SIGNAL_EXIT
closed 858 trades on the 2022-2025 holdout at a 10% win rate. The proposed
remedy is a hard maximum holding period. These tests pin the mechanism down so
that a sweep of the parameter is measuring the time stop rather than something
adjacent to it.

Every test here has been sabotage-verified: the exit branch was deliberately
broken and each assertion below was confirmed to fail.
"""

from datetime import datetime, timedelta, timezone
import unittest

from quantlab.backtest import CostModel
from quantlab.models import Bar
from quantlab.portfolio import LongOnlyPortfolioBacktester, MoneyManagement


def _policy(**overrides) -> MoneyManagement:
    base = {
        "risk_per_trade": 0.02,
        "maximum_position_fraction": 0.90,
        "stop_loss_pct": 0.50,
        # Both far enough away that neither can fire, so a closed trade can only
        # be the signal or the time stop.
        "take_profit_pct": 50.0,
        "minimum_confidence": 0.25,
        "maximum_concurrent_assets": 5,
        "minimum_order_notional": 1.0,
        "minimum_position_fraction": 0.0,
        "volatility_target": 1.0,
        "minimum_daily_quote_volume": 0.0,
        "maximum_volume_participation": 1.0,
        "drawdown_deleverage_start": 0.25,
    }
    base.update(overrides)
    return MoneyManagement(**base)


def _flat_daily_bars(count: int = 40) -> list[Bar]:
    """Daily bars that barely move, so no price-based exit can trigger."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(days=index),
            open=100.0,
            high=100.5,
            low=99.5,
            close=100.0,
            volume=1_000_000.0,
        )
        for index in range(count)
    ]


class _AlwaysLong:
    """Constant full confidence: the signal never asks to exit, so anything
    that closes a position came from money management."""

    def reset(self) -> None:
        pass

    def on_bar(self, bars: list[Bar]) -> float:
        return 1.0


def _run(policy: MoneyManagement, bars: list[Bar]):
    return LongOnlyPortfolioBacktester(CostModel(0.0, 0.0), policy).run(
        {"AAA": bars}, _AlwaysLong, 100_000.0
    )


class TimeStopTest(unittest.TestCase):
    def test_no_time_stop_by_default(self) -> None:
        """A policy that does not ask for a time stop must never produce one --
        this is what keeps every stored historical result unchanged."""
        result = _run(_policy(), _flat_daily_bars())
        self.assertIsNone(_policy().maximum_holding_days)
        self.assertEqual([t for t in result.trades if t.exit_reason == "TIME_STOP"], [])

    def test_positions_are_closed_once_they_age_out(self) -> None:
        result = _run(_policy(maximum_holding_days=3), _flat_daily_bars())
        timed = [t for t in result.trades if t.exit_reason == "TIME_STOP"]
        self.assertTrue(timed, "an aged position was never closed by the time stop")
        for trade in timed:
            held = (trade.exit_time - trade.entry_time).days
            # It fires on the first bar at or past the limit, so the realised
            # duration is the limit itself on daily bars. Asserting equality
            # rather than `<=` is deliberate: a stop that fires late by one bar
            # still satisfies an inequality and is still a bug.
            self.assertEqual(
                held,
                3,
                f"time stop fired after {held} days under a 3-day limit",
            )

    def test_a_shorter_limit_closes_sooner(self) -> None:
        """The parameter has to actually move the exit, not just exist."""
        short = _run(_policy(maximum_holding_days=2), _flat_daily_bars())
        long = _run(_policy(maximum_holding_days=10), _flat_daily_bars())
        short_held = [(t.exit_time - t.entry_time).days for t in short.trades]
        long_held = [(t.exit_time - t.entry_time).days for t in long.trades]
        self.assertTrue(short_held and long_held)
        self.assertEqual(max(short_held), 2)
        self.assertEqual(max(long_held), 10)
        # A tighter limit must recycle capital more often, or the parameter is
        # doing nothing observable.
        self.assertGreater(len(short.trades), len(long.trades))

    def test_the_signal_still_owns_its_own_exits(self) -> None:
        """A position the signal wants to close is attributed to the signal, so
        the TIME_STOP count measures overrides rather than coincidences."""

        class _ExitsOnDayTwo:
            def __init__(self) -> None:
                self.seen = 0

            def reset(self) -> None:
                self.seen = 0

            def on_bar(self, bars: list[Bar]) -> float:
                self.seen += 1
                return 1.0 if self.seen <= 2 else 0.0

        result = LongOnlyPortfolioBacktester(
            CostModel(0.0, 0.0), _policy(maximum_holding_days=3)
        ).run({"AAA": _flat_daily_bars()}, _ExitsOnDayTwo, 100_000.0)
        self.assertTrue(result.trades)
        self.assertEqual(
            {t.exit_reason for t in result.trades},
            {"SIGNAL_EXIT"},
            "the time stop stole an exit the signal had already asked for",
        )

    def test_zero_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _policy(maximum_holding_days=0)


if __name__ == "__main__":
    unittest.main()
