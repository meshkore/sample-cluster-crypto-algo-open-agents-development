"""The autonomous path, exactly as an agent walks it.

An agent writes a strategy, registers it, and launches it. Nothing is mocked:
a real backtester process is started as a subprocess on a real port, the loop
pulls candles over HTTP, and the result is read back from the service and
persisted under its id.

This is the test that would catch the architecture drifting back to something
only a human at a terminal can drive.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import socket
import unittest

from quantlab_manager.orchestration import BacktesterProcess, Orchestrator
from quantlab_trading import brains
from quantlab_trading.runner import Decision

UTC = timezone.utc


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _candles(closes):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        {
            "timestamp": (start + timedelta(days=i)).isoformat(),
            "open": c,
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "volume": 5_000_000.0,
        }
        for i, c in enumerate(closes)
    ]


@brains.register("test-buyhold", "Buys once on the second bar and holds.")
class _BuyAndHold:
    def __init__(self, notional: float = 1000.0):
        self.notional = notional

    def decide(self, tick):
        decision = Decision()
        if tick["sequence"] == 1 and not tick["account"]["positions"]:
            decision.buy("AAA", self.notional, "ENTRY", "opening position")
        else:
            decision.note = "holding"
        return decision


@brains.register("test-quitter", "Stops on its own mandate after five bars.")
class _Quitter:
    def decide(self, tick):
        decision = Decision()
        if tick["sequence"] >= 5:
            decision.stop = "mandate breached"
        return decision


class OrchestrationTest(unittest.TestCase):
    """One backtester process for the class; launches reuse it, as in real use."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.port = _free_port()
        cls.lab = Orchestrator(database=Path(cls.tmp.name) / "lab.db", port=cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.lab.close()
        cls.tmp.cleanup()

    def _launch(self, strategy, closes, **kwargs):
        return self.lab.launch(
            strategy,
            candles={"AAA": _candles(closes)},
            capital=10_000.0,
            commission_bps=0.0,
            slippage_bps=0.0,
            **kwargs,
        )

    def test_a_registered_strategy_is_discoverable(self):
        names = {entry["name"] for entry in self.lab.strategies()}
        self.assertIn("test-buyhold", names)
        self.assertIn("mandate", names)

    def test_registering_a_clashing_name_is_refused(self):
        """Silently replacing would merge two agents' work and the loser would
        still look as though it had been tested."""
        with self.assertRaises(ValueError):

            @brains.register("test-buyhold")
            class _Other:
                def decide(self, tick):
                    return Decision()

    def test_an_agent_launches_a_strategy_and_gets_a_persisted_run(self):
        rising = [100.0 * (1.01**i) for i in range(30)]
        result = self._launch("test-buyhold", rising, label="agent-run")

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["label"], "agent-run")
        self.assertEqual(result["submitted_by"], "agent")
        self.assertGreater(result["final_equity"], 10_000.0)

        backtest_id = result["backtest_id"]
        self.assertEqual(len(self.lab.store.orders(backtest_id)), 1)
        self.assertEqual(len(self.lab.store.equity(backtest_id)), 30)
        decisions = self.lab.store.decisions(backtest_id)
        self.assertTrue(any(d["note"] == "holding" for d in decisions))
        acted = next(d for d in decisions if d["orders"])
        self.assertEqual(acted["orders"][0]["rationale"], "opening position")

    def test_the_backtester_is_started_once_and_reused(self):
        """Sessions live in the server's memory, so a second process on the same
        port would serve a different set of runs and ids would appear to vanish."""
        self.assertTrue(self.lab.service.healthy())
        first = self._launch("test-buyhold", [100.0] * 12, label="reuse-a")
        second = self._launch("test-buyhold", [101.0] * 12, label="reuse-b")
        # Different tapes must be different runs. Fingerprinting symbol
        # NAMES alone made these collide and the second overwrote the first.
        self.assertNotEqual(first["backtest_id"], second["backtest_id"])
        self.assertEqual(
            len(self.lab.store.runs()),
            len(set(row["backtest_id"] for row in self.lab.store.runs())),
        )

    def test_a_brain_stopping_itself_is_recorded(self):
        result = self._launch("test-quitter", [100.0] * 40, label="quit")
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["aborted"], 1)
        self.assertIn("mandate", result["abort_reason"])

    def test_parameters_reach_the_brain_and_the_record(self):
        result = self._launch(
            "test-buyhold",
            [100.0] * 20,
            label="params",
            parameters={"notional": 2500.0},
        )
        self.assertEqual(result["strategy_family"], "test-buyhold")
        self.assertIn("2500", result["strategy_params_json"])
        orders = self.lab.store.orders(result["backtest_id"])
        self.assertAlmostEqual(orders[0]["notional"], 2500.0)

    def test_an_unknown_strategy_names_the_ones_that_exist(self):
        with self.assertRaises(KeyError) as caught:
            self._launch("no-such-brain", [100.0] * 5)
        self.assertIn("Available", str(caught.exception))

    def test_a_crashing_brain_leaves_a_failed_row_and_re_raises(self):
        @brains.register("test-broken", "Raises on the first tick.")
        class _Broken:
            def decide(self, tick):
                raise ZeroDivisionError("boom")

        with self.assertRaises(ZeroDivisionError):
            self._launch("test-broken", [100.0] * 10, label="broken")
        failed = [r for r in self.lab.store.runs() if r["label"] == "broken"]
        self.assertEqual(failed[0]["status"], "failed")
        self.assertIn("ZeroDivisionError", failed[0]["abort_reason"])


class ProgressTest(unittest.TestCase):
    """A run has to be readable WHILE it runs, or "live" is just a word.

    Everything a run produced used to land in one write at the end, so a
    backtest in flight was a row saying `running` with nothing behind it. The
    monitor could name it and show nothing -- and the page opened an SSE stream
    at a route the daemon has never served, so nobody noticed.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.lab = Orchestrator(
            database=Path(cls.tmp.name) / "lab.db", port=_free_port()
        )

    @classmethod
    def tearDownClass(cls):
        cls.lab.close()
        cls.tmp.cleanup()

    def _run(self, **kwargs):
        rising = [100.0 * (1.01**i) for i in range(40)]
        return self.lab.launch(
            "test-buyhold",
            candles={"AAA": _candles(rising)},
            capital=10_000.0,
            commission_bps=0.0,
            slippage_bps=0.0,
            **kwargs,
        )

    def test_a_watched_run_is_readable_before_it_finishes(self):
        import quantlab_manager.orchestration as orchestration

        seen = []
        original = orchestration.PROGRESS_SECONDS
        orchestration.PROGRESS_SECONDS = 0.0  # snapshot every bar, for the test
        try:

            def watch(tick):
                if tick["sequence"] != 30:
                    return
                # Exactly what the monitor's left rail asks for, mid-run.
                live = self.lab.store.sidebar()["live"]
                if live:
                    seen.append(
                        (live[0], len(self.lab.store.equity(live[0]["backtest_id"])))
                    )

            result = self._run(progress=True, on_tick=watch)
        finally:
            orchestration.PROGRESS_SECONDS = original

        self.assertTrue(seen, "the run never appeared in the live list")
        row, points = seen[-1]
        self.assertEqual(row["backtest_id"], result["backtest_id"])
        self.assertEqual(row["status"], "running", "a run in flight must say so")
        self.assertGreater(points, 0, "a watched run must have a curve to draw")
        self.assertLess(points, 40, "a mid-run snapshot is not the whole run")
        self.assertIsNotNone(row["updated_at"], "the page re-reads on this stamp")
        # and the final write is still authoritative
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(self.lab.store.equity(result["backtest_id"])), 40)

    def test_an_unwatched_run_writes_nothing_until_it_finishes(self):
        """Six hundred runs inside a search must not each write forty times."""
        writes = []
        real = self.lab._write

        def counted(wire, backtest_id, stop, final=True, publish=True):
            writes.append(final)
            return real(wire, backtest_id, stop, final=final, publish=publish)

        self.lab._write = counted
        try:
            self._run()
        finally:
            self.lab._write = real

        self.assertEqual(writes, [True], "an unwatched run wrote more than once")

    def test_a_failing_snapshot_cannot_kill_the_run(self):
        """An observation that can stop what it observes is worse than none."""
        import quantlab_manager.orchestration as orchestration

        original = orchestration.PROGRESS_SECONDS
        orchestration.PROGRESS_SECONDS = 0.0
        real = self.lab._write

        def explode(wire, backtest_id, stop, final=True, publish=True):
            if not final:
                raise RuntimeError("the monitor fell over")
            return real(wire, backtest_id, stop, final=final, publish=publish)

        self.lab._write = explode
        try:
            result = self._run(progress=True)
        finally:
            self.lab._write = real
            orchestration.PROGRESS_SECONDS = original

        self.assertEqual(result["status"], "complete")


class ProcessSupervisionTest(unittest.TestCase):
    def test_it_reports_unhealthy_when_nothing_is_listening(self):
        service = BacktesterProcess(port=_free_port())
        self.assertFalse(service.healthy(timeout=0.5))

    def test_stop_is_safe_when_it_started_nothing(self):
        """It must never kill a server it did not start."""
        service = BacktesterProcess(port=_free_port())
        service.stop()
        self.assertIsNone(service.process)


if __name__ == "__main__":
    unittest.main()
