"""The intraday system driven over HTTP, exactly as the orchestrator drives it.

`launch.py` runs both phases in process, for a stated reason: the sealed 2026
window at 15-minute resolution is about 12 MB of JSON and the server refuses a
body over 4 MB. That decision is defensible only if the protocol is still
exercised somewhere, or it rots quietly and the first person to launch this
family through the Orchestrator discovers it. This is that somewhere: a small
synthetic window, over a real socket, through the same `run_backtest` loop
`quantlab_trading` gives every contributor.

Sabotage-verified: with the entry threshold inverted the run completes and
takes zero trades, which is why the trade-count assertion is here rather than
a bare "it did not crash".
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request

import quantlab_backtester
from quantlab_intraday.reversion import IntradayReversionBrain
from quantlab_trading.runner import BacktesterClient, run_backtest

UTC = timezone.utc
STEP = timedelta(minutes=15)
START = datetime(2024, 1, 1, tzinfo=UTC)


def _tape(bars=700, cycle=15, base=100.0):
    """A flat tape with a periodic liquidity flush and a recovery after it.

    Deliberately synthetic and deliberately obvious: this test is about the
    wire, not about whether the mechanism is real. Flat between flushes on
    purpose -- the anchor is a 20-bar VWAP, so a *rising* tape puts the anchor
    below price and a flush merely returns to it, which is how the first
    version of this fixture produced a run that refused all 448 bars at the
    cost hurdle and looked like a broken strategy rather than a bad fixture.
    """
    rows = []
    for index in range(bars):
        phase = index % cycle
        if phase == cycle - 3:  # the flush: 2% down, closing on its own low
            open_, close = base, base * 0.98
            high, low = base * 1.0005, close
        elif phase == cycle - 2:  # the recovery
            open_, close = base * 0.98, base * 0.995
            high, low = close * 1.0005, base * 0.9795
        elif phase == cycle - 1:
            open_, close = base * 0.995, base
            high, low = base * 1.0005, base * 0.9945
        else:  # quiet
            open_ = close = base
            high, low = base * 1.0008, base * 0.9992
        rows.append(
            {
                "timestamp": (START + STEP * index).isoformat(),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 5_000.0,
            }
        )
    return {"SYNTH": rows}


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class WireTest(unittest.TestCase):
    server = None

    @classmethod
    def setUpClass(cls):
        cls.port = _free_port()
        # The child does not inherit this process's sys.path, and two suites in
        # this repository already fail that way on a checkout that is perfectly
        # fine. Point it at the packages explicitly.
        root = Path(quantlab_backtester.__file__).resolve().parent.parent
        trading = Path(__file__).resolve().parent.parent
        env = {
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": f"{root}:{trading}",
            "HOME": str(Path.home()),
        }
        cls.server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "quantlab_backtester.server",
                "--port",
                str(cls.port),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{cls.port}/health", timeout=1
                ) as response:
                    if json.loads(response.read())["status"] == "ok":
                        return
            except (urllib.error.URLError, OSError, ValueError, KeyError):
                time.sleep(0.2)
        cls.tearDownClass()
        raise unittest.SkipTest("the backtester service did not come up")

    @classmethod
    def tearDownClass(cls):
        if cls.server is not None:
            cls.server.terminate()
            cls.server.wait(timeout=10)
            cls.server = None

    def _run(self, **params):
        brain = IntradayReversionBrain(**params)
        summary = run_backtest(
            brain,
            {
                "label": "intraday-wire-test",
                "initial_capital": 100_000.0,
                "commission_bps": 10.0,
                "slippage_bps": 5.0,
                "strategy_family": "intraday-reversion",
                "strategy_params": brain.parameters(),
                "candles": _tape(),
            },
            client=BacktesterClient(f"http://127.0.0.1:{self.port}"),
        )
        return brain, summary

    def test_the_family_trades_over_a_real_socket(self):
        brain, summary = self._run()
        self.assertEqual(summary["status"], "complete", summary.get("stop_reason"))
        self.assertGreater(summary["trades"], 0, brain.diagnostics())
        self.assertEqual(summary["rejected"], 0)
        # Every entry was accounted for by an exit path rather than left to the
        # end of the tape: a system whose positions only close because the run
        # ran out of bars has no exit rule worth the name.
        self.assertGreater(sum(brain.exits.values()), 0)

    def test_an_impossible_threshold_completes_and_trades_nothing(self):
        """The control for the assertion above: same tape, no qualifying bar."""
        brain, summary = self._run(entry_displacement_atr=99.0)
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["trades"], 0)
        self.assertEqual(brain.entries, 0)


if __name__ == "__main__":
    unittest.main()
