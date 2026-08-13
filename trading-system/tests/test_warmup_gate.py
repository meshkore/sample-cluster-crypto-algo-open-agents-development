"""The harness refuses orders on bars served only to warm the filters up.

Written after generation 4 -- a strategy this laboratory's own loop is meant to
write unattended -- opened 17 positions between September and December 2025
inside a run whose `trade_from` was 2026-01-01, and published the result as a
sealed 2026 measurement. The two hand-written brains each gate themselves and
are correct; nothing checked that a third one did.

What makes it worth a test rather than a fix is how quietly it failed. Those 17
trades netted -109 on 100,000, so every published figure still looked ordinary
and the pre-lock trades were visible only by reading entry dates one by one. A
strategy that happened to be profitable in the warm-up would have reported
training performance as forward performance with nothing to show for it.

Sabotage-verified: deleting the `moment < opens` branch in `launch._drive`
turns `test_a_brain_with_no_gate_cannot_trade_the_warmup` red.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from quantlab_intraday import launch

UTC = timezone.utc
OPENS = datetime(2026, 1, 1, tzinfo=UTC)

# A well-formed buy. The point of these tests is where an order is allowed to
# reach the book, not what is in it, so this is the minimum the session accepts.
ORDER = {"symbol": "BTCUSDT", "side": "buy", "quantity": 1.0, "reason": "test"}


@dataclass
class Decision:
    orders: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""
    stop: str = ""


class UngatedBrain:
    """A brain that buys on every tick it is shown. Exactly the bug."""

    def __init__(self, trade_from: str) -> None:
        self.params = {"trade_from": trade_from}
        self.seen = 0

    def parameters(self) -> dict[str, Any]:
        return dict(self.params)

    def decide(self, tick: dict[str, Any]) -> Decision:
        self.seen += 1
        return Decision(orders=[dict(ORDER)])


class FakeSession:
    """Enough of `BacktestSession` to drive it: ticks in, submissions out."""

    def __init__(self, stamps: list[datetime]) -> None:
        self.stamps = list(stamps)
        self.index = 0
        self.submitted: list[tuple[int, str]] = []
        self.notes: list[str] = []

    def next_tick(self) -> dict[str, Any]:
        if self.index >= len(self.stamps):
            return {"done": True}
        stamp = self.stamps[self.index]
        self.index += 1
        return {"timestamp": stamp.isoformat(), "candles": {}, "indicators": {}}

    def submit(self, orders: list[Any], note: str) -> None:
        self.submitted.append((len(orders), note))
        if note:
            self.notes.append(note)

    def stop(self, reason: str) -> None:  # pragma: no cover - not exercised here
        raise AssertionError(f"unexpected stop: {reason}")


def _stamps(before: int, after: int) -> list[datetime]:
    """`before` bars of warm-up, then `after` bars the brain may trade."""
    warm = [OPENS - timedelta(days=before - i) for i in range(before)]
    live = [OPENS + timedelta(days=i) for i in range(after)]
    return warm + live


class TheWarmupGate(unittest.TestCase):
    def test_a_brain_with_no_gate_cannot_trade_the_warmup(self):
        """The load-bearing one. Everything else here is a guard around it."""
        session = FakeSession(_stamps(before=5, after=3))
        brain = UngatedBrain(OPENS.isoformat())

        withheld = launch._drive(session, brain)

        self.assertEqual(withheld, 5)
        traded = [count for count, _ in session.submitted if count]
        self.assertEqual(len(traded), 3, "only the post-open bars may trade")

    def test_the_brain_still_sees_every_warmup_bar(self):
        """Withholding by not showing the brain the ticks would be a different
        bug wearing this fix's clothes: a 30-day moving average that starts on
        the first tradeable bar is cold for a month and refuses everything."""
        session = FakeSession(_stamps(before=5, after=3))
        brain = UngatedBrain(OPENS.isoformat())

        launch._drive(session, brain)

        self.assertEqual(brain.seen, 8)

    def test_the_refusal_is_recorded_rather_than_silent(self):
        """A gate that drops orders without saying so is indistinguishable from
        a strategy that had no signal, which is the reading that cost a night."""
        session = FakeSession(_stamps(before=2, after=1))
        launch._drive(session, UngatedBrain(OPENS.isoformat()))

        self.assertTrue(any("withheld" in note for note in session.notes))

    def test_a_run_with_no_trade_from_is_left_alone(self):
        """Block runs and ad-hoc sessions do not always set one. Refusing every
        order in that case would silently empty them."""
        session = FakeSession(_stamps(before=4, after=2))
        brain = UngatedBrain("")

        withheld = launch._drive(session, brain)

        self.assertEqual(withheld, 0)
        self.assertEqual(len([c for c, _ in session.submitted if c]), 6)

    def test_a_gated_brain_is_unaffected(self):
        """The built-in brains already refuse warm-up bars themselves. The
        harness must not double-count or otherwise disturb them."""

        class GatedBrain(UngatedBrain):
            def decide(self, tick):
                self.seen += 1
                moment = datetime.fromisoformat(tick["timestamp"])
                if moment < OPENS:
                    return Decision(note="warming")
                return Decision(orders=[dict(ORDER)])

        session = FakeSession(_stamps(before=4, after=2))
        withheld = launch._drive(session, GatedBrain(OPENS.isoformat()))

        self.assertEqual(withheld, 0)
        self.assertEqual(len([c for c, _ in session.submitted if c]), 2)


if __name__ == "__main__":
    unittest.main()
