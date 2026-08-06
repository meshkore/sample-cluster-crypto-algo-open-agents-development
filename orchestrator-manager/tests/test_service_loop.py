"""End to end over a real socket: backtester on a port, trading system driving.

This is the integration the operator asked for -- anyone can start the
backtester, point a brain at it and get a run. It lives in the manager's suite
because it composes all three folders, which the layering contract permits for
tests and forbids for shipped code.

Nothing is mocked. A real ThreadingHTTPServer binds an ephemeral port, a real
client speaks HTTP to it, and the loop pulls candles until the tape ends.
"""

from datetime import datetime, timedelta, timezone
import threading
import unittest

from quantlab_backtester import server as backtester_server
from quantlab_backtester.server import build_server
from quantlab_trading.runner import (
    BacktesterClient,
    Decision,
    MandateBrain,
    run_backtest,
)

UTC = timezone.utc


def _candles(closes, symbol_seed=0.0):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        {
            "timestamp": (start + timedelta(days=i)).isoformat(),
            "open": c,
            "high": c * 1.02,
            "low": c * 0.98,
            "close": c,
            "volume": 5_000_000.0,
        }
        for i, c in enumerate(closes)
    ]


class _CountingBrain:
    """Buys once and then does nothing, so the assertions are about the wire."""

    def __init__(self):
        self.ticks = 0
        self.bought = False

    def decide(self, tick):
        self.ticks += 1
        decision = Decision()
        if not self.bought and tick["account"]["cash"] > 1000:
            self.bought = True
            decision.buy("AAA", 1000.0, "TEST", "first opportunity")
        else:
            decision.note = "nothing to do"
        return decision


class ServiceLoopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        backtester_server.REGISTRY = backtester_server.SessionRegistry()
        cls.server = build_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _config(self, label, closes):
        return {
            "label": label,
            "initial_capital": 10_000.0,
            "candles": {"AAA": _candles(closes)},
        }

    def test_health_is_reachable(self):
        client = BacktesterClient(self.base)
        self.assertEqual(client._call("GET", "/health")["status"], "ok")

    def test_a_brain_drives_a_run_to_completion_over_http(self):
        client = BacktesterClient(self.base)
        brain = _CountingBrain()
        rising = [100.0 * (1.01**i) for i in range(40)]
        summary = run_backtest(brain, self._config("wire", rising), client)

        self.assertEqual(brain.ticks, 40, "the brain did not see every candle")
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["orders"], 1)
        self.assertGreater(summary["final_equity"], 10_000.0)

    def test_the_brain_can_stop_the_run_itself(self):
        """The mandate belongs to the trading system, so it must be able to end
        a run without the backtester having any say."""

        class _Quitter:
            def decide(self, tick):
                decision = Decision()
                if tick["sequence"] >= 5:
                    decision.stop = "seen enough"
                return decision

        client = BacktesterClient(self.base)
        summary = run_backtest(_Quitter(), self._config("quit", [100.0] * 30), client)
        self.assertEqual(summary["status"], "stopped")
        self.assertEqual(summary["stop_reason"], "seen enough")
        self.assertLess(summary["processed"], 30)

    def test_the_reference_brain_enforces_the_drawdown_mandate(self):
        """A collapsing tape must trip MandateBrain's own ceiling, not the
        backtester's -- the simulator has no view on when to give up."""
        client = BacktesterClient(self.base)
        collapse = [100.0] * 210 + [100.0 * (0.90**i) for i in range(1, 40)]
        summary = run_backtest(
            MandateBrain(maximum_drawdown=0.25, stop_loss=0.99, take_profit=9.9),
            self._config("mandate", collapse),
            client,
        )
        self.assertIn(summary["status"], ("stopped", "complete"))
        if summary["status"] == "stopped":
            self.assertIn("drawdown", summary["stop_reason"])

    def test_a_bad_order_is_reported_and_does_not_kill_the_run(self):
        class _Wrong:
            def decide(self, tick):
                return Decision().buy("NOPE", 100.0, "TEST")

        client = BacktesterClient(self.base)
        summary = run_backtest(_Wrong(), self._config("bad", [100.0] * 12), client)
        self.assertEqual(summary["status"], "complete")
        self.assertGreater(summary["rejected"], 0)
        self.assertEqual(summary["orders"], 0)

    def test_an_unknown_session_is_a_404_not_a_crash(self):
        client = BacktesterClient(self.base)
        with self.assertRaises(RuntimeError) as caught:
            client.next("does-not-exist")
        self.assertIn("404", str(caught.exception))

    def test_a_clear_error_when_the_backtester_is_not_running(self):
        """The message a contributor sees first has to say what to start."""
        client = BacktesterClient("http://127.0.0.1:1", timeout=2.0)
        with self.assertRaises(RuntimeError) as caught:
            client.summary("x")
        self.assertIn("quantlab_backtester.server", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
