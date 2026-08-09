"""The loop: attribution, module targeting, the lock, and never stopping.

The failure that matters here is not "an iteration produced a bad strategy" --
that is the expected case and the ledger is full of them. It is an iteration
that stops the loop, repeats a dead idea, spends the forward window twice, or
moves the incumbent on a result that did not beat it.

All sabotage-verified.
"""

import json
import tempfile
import unittest
from pathlib import Path

from quantlab_manager.advisors import validate_critique, validate_proposal
from quantlab_manager.diagnosis import attribute, diagnose
from quantlab_manager.loop import MODULE_KEYS, LoopState, ResearchLoop, module_space
from quantlab_manager.team import TEAM


def _order(symbol, at, side, reason):
    return {"symbol": symbol, "timestamp": at, "side": side, "reason": reason}


def _trade(symbol, at, pnl, exit_reason="SIGNAL_EXIT"):
    return {
        "symbol": symbol,
        "entry_time": at,
        "exit_time": at,
        "pnl": pnl,
        "pnl_pct": pnl / 1000.0,
        "exit_reason": exit_reason,
    }


class TestAttribution(unittest.TestCase):
    def test_the_module_that_opened_a_trade_owns_its_result(self):
        orders = [
            _order("AAA", "2026-01-01", "BUY", "BEAR_PARTICIPATION"),
            _order("BBB", "2026-01-02", "BUY", "BULL_TREND"),
        ]
        trades = [
            _trade("AAA", "2026-01-01", -500.0),
            _trade("BBB", "2026-01-02", 300.0),
        ]
        split = attribute(orders, trades, 100_000.0)
        self.assertAlmostEqual(split["by_module"]["BEAR"]["contribution"], -0.005)
        self.assertAlmostEqual(split["by_module"]["BULL"]["contribution"], 0.003)

    def test_a_symbol_traded_twice_is_attributed_twice_and_correctly(self):
        """Sabotage: key the entry reason on the symbol alone. The second trade
        then inherits the first's module and a losing bear entry is credited to
        the bull branch -- which is the exact mistake that would send the loop
        to work on the wrong piece."""
        orders = [
            _order("AAA", "2026-01-01", "BUY", "BULL_TREND"),
            _order("AAA", "2026-03-01", "BUY", "BEAR_PARTICIPATION"),
        ]
        trades = [
            _trade("AAA", "2026-01-01", 400.0),
            _trade("AAA", "2026-03-01", -900.0),
        ]
        split = attribute(orders, trades, 100_000.0)
        self.assertEqual(split["by_module"]["BULL"]["trades"], 1)
        self.assertEqual(split["by_module"]["BEAR"]["trades"], 1)
        self.assertAlmostEqual(split["by_module"]["BEAR"]["contribution"], -0.009)

    def test_an_exit_reason_is_not_mistaken_for_a_module(self):
        orders = [_order("AAA", "2026-01-01", "BUY", "TAKE_PROFIT")]
        trades = [_trade("AAA", "2026-01-01", 10.0)]
        split = attribute(orders, trades, 100_000.0)
        self.assertIn("UNATTRIBUTED", split["by_module"])


class _Store:
    def __init__(self, run, orders, trades):
        self._run, self._orders, self._trades = run, orders, trades

    def run(self, backtest_id):
        return self._run if backtest_id == self._run["backtest_id"] else None

    def orders(self, backtest_id, limit=0):
        return self._orders

    def trades(self, backtest_id, limit=0):
        return self._trades

    def runs(self, limit=0):
        return [self._run]


class TestDiagnosis(unittest.TestCase):
    def _run(self, **overrides):
        base = {
            "backtest_id": "abc",
            "label": "forward",
            "window_start": "2022-01-01",
            "window_end": "2026-12-31",
            "return_pct": -0.0678,
            "max_drawdown": 0.0727,
            "trades": 2,
            "initial_capital": 100_000.0,
        }
        base.update(overrides)
        return base

    def test_it_targets_the_module_that_lost_the_money(self):
        """The whole point of the stage. Sabotage: pick the module with the most
        TRADES instead of the worst contribution, and the loop spends its
        iterations improving the piece that was already working."""
        store = _Store(
            self._run(),
            [
                _order("AAA", "2026-01-01", "BUY", "BEAR_PARTICIPATION"),
                _order("BBB", "2026-01-02", "BUY", "BULL_TREND"),
                _order("CCC", "2026-01-03", "BUY", "BULL_TREND"),
            ],
            [
                _trade("AAA", "2026-01-01", -5_000.0),
                _trade("BBB", "2026-01-02", 100.0),
                _trade("CCC", "2026-01-03", 120.0),
            ],
        )
        report = diagnose(store, "abc")
        self.assertEqual(report["target_module"], "BEAR")
        self.assertEqual(report["worst_module"], "BEAR")

    def test_a_run_with_no_trades_blames_the_gate_not_the_entry_rule(self):
        """A gated run has not failed to find a signal; it was never allowed to
        look. Sending the loop to rewrite the entry rule would be an iteration
        spent on the wrong thing."""
        store = _Store(self._run(trades=0, return_pct=0.0), [], [])
        report = diagnose(store, "abc")
        self.assertEqual(report["target_module"], "DETECTOR")
        self.assertIn("gated", report["findings"][0])

    def test_a_profitable_run_pushes_the_best_module_rather_than_repairing_one(self):
        store = _Store(
            self._run(return_pct=0.3),
            [_order("AAA", "2026-01-01", "BUY", "SIDEWAYS_DEVIATION")],
            [_trade("AAA", "2026-01-01", 4_000.0)],
        )
        report = diagnose(store, "abc")
        self.assertEqual(report["target_module"], "SIDEWAYS")


class TestModuleTargeting(unittest.TestCase):
    def test_an_iteration_may_only_move_its_own_module(self):
        """Improving a system by changing everything at once produces a number
        nobody can attribute."""
        space, slots = module_space("BEAR")
        names = {d.name for d in space.dimensions}
        self.assertTrue(all(n.startswith("bear_") for n in names), names)
        self.assertFalse(any(n.startswith("bull_") for n in names))
        self.assertEqual(slots, ("bear_entry_rule", "bear_exit_rule"))

    def test_the_branch_is_forced_to_the_evolved_rule(self):
        """Sabotage: leave `bear_rule` free. The search escapes into the six
        hand-written mechanisms and the grammar is never exercised, so an
        iteration that claims to have invented something has not."""
        space, _ = module_space("BEAR")
        rule = next(d for d in space.dimensions if d.name == "bear_rule")
        self.assertEqual(rule.choices, ("evolved",))

    def test_the_detector_moves_thresholds_and_has_no_rule_slots(self):
        space, slots = module_space("DETECTOR")
        self.assertEqual(slots, ())
        self.assertIn("bear_min_depth", {d.name for d in space.dimensions})

    def test_every_module_has_a_key_list(self):
        for module in ("BULL", "SIDEWAYS", "BEAR", "DETECTOR"):
            self.assertIn(module, MODULE_KEYS)


class TestLedgerAwareness(unittest.TestCase):
    def _loop(self, directory):
        ledger = Path(directory) / "hypotheses.jsonl"
        ledger.write_text(
            json.dumps({"id": "H-1", "config_fingerprint": "deadbeef"})
            + "\n"
            + json.dumps({"id": "H-2", "verdict": "REFUTED", "statement": "no"})
            + "\n"
        )
        return ResearchLoop(
            lab_fit=None,
            lab_forward=None,
            store=None,
            symbols=["BTCUSDT"],
            repository=directory,
            state_path=Path(directory) / "state.json",
            ledger_path=ledger,
        )

    def test_it_knows_what_has_already_been_tried(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self._loop(directory).tried(), {"deadbeef"})

    def test_a_corrupt_ledger_line_does_not_stop_the_loop(self):
        """Re-running dead ideas is the only way a loop like this fails, but so
        is refusing to start because one line is malformed."""
        with tempfile.TemporaryDirectory() as directory:
            loop = self._loop(directory)
            with loop.ledger_path.open("a") as handle:
                handle.write("{not json\n")
            # The bad line is skipped and the good records survive. Wrapping the
            # whole read in one try discarded everything after the first bad
            # line, and a loop that has forgotten what it tried re-runs it.
            self.assertEqual(loop.tried(), {"deadbeef"})
            self.assertEqual([r["id"] for r in loop.ledger_tail()], ["H-1", "H-2"])

    def test_state_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            loop = self._loop(directory)
            loop.state.iteration = 7
            loop.state.incumbent = {"bear_weight": 0.4}
            loop.state.incumbent_forward = 0.02
            loop._save()
            restored = LoopState.load(loop.state_path)
            self.assertEqual(restored.iteration, 7)
            self.assertEqual(restored.incumbent, {"bear_weight": 0.4})
            self.assertEqual(restored.incumbent_forward, 0.02)


class TestAdvisorValidation(unittest.TestCase):
    def test_a_proposal_naming_an_unknown_module_is_dropped(self):
        self.assertIsNone(validate_proposal({"module": "MOON", "claim": "x"}))

    def test_an_invalid_rule_is_dropped_and_the_proposal_survives(self):
        """One bad tree is not a reason to discard a good hypothesis. Sabotage:
        reject the whole proposal on the first bad rule, and a model that emits
        three good rules and one typo contributes nothing."""
        proposal = validate_proposal(
            {
                "module": "bear",
                "claim": "c",
                "seed_rules": [
                    {
                        "t": "gt",
                        "a": {"t": "px", "name": "close"},
                        "b": {"t": "col", "name": "sma_200"},
                    },
                    {
                        "t": "gt",
                        "a": {"t": "col", "name": "moon_phase"},
                        "b": {"t": "num", "v": 1},
                    },
                    {
                        "t": "gt",
                        "a": {"t": "px", "name": "low"},
                        "b": {"t": "px", "name": "low"},
                    },
                ],
            }
        )
        self.assertEqual(proposal["module"], "BEAR")
        self.assertEqual(len(proposal["seed_rules"]), 1)

    def test_nothing_unrecognised_reaches_the_search(self):
        """A proposal is untrusted input. Sabotage: `return proposal` verbatim
        and an advisor can put arbitrary keys into the genome."""
        proposal = validate_proposal(
            {
                "module": "BULL",
                "claim": "c",
                "shell": "rm -rf /",
                "trade_from": "2026-01-01",
            }
        )
        self.assertEqual(
            set(proposal),
            {"module", "claim", "kill_condition", "reasoning", "seed_rules"},
        )

    def test_an_unparseable_critique_is_not_a_silent_pass(self):
        self.assertIsNone(validate_critique("refuted!"))
        self.assertTrue(validate_critique({"refuted": True})["refuted"])


class TestTeam(unittest.TestCase):
    def test_exactly_one_member_may_write_code(self):
        """The operator's rule, pinned. If a second member ever gains write
        authority it should be a deliberate edit here, visible in the diff."""
        authors = [m.handle for m in TEAM if m.writes_code]
        self.assertEqual(authors, ["blackmac-quantlab-proposer-opus5"])

    def test_every_handle_is_namespaced_to_this_machine(self):
        for member in TEAM:
            self.assertTrue(member.handle.startswith("blackmac-"), member.handle)


if __name__ == "__main__":
    unittest.main()


class TestTokenBudget(unittest.TestCase):
    """Tokens are finite; the loop is not.

    The operator's requirement: when a provider runs out, sit out its window and
    keep working without it. Nothing here may stop the loop -- the mechanical
    proposer is weaker than a model and it is still a real iteration.
    """

    def test_a_quota_response_is_recognised_however_it_is_dressed(self):
        from quantlab_manager.advisors import looks_exhausted

        self.assertTrue(looks_exhausted(429, ""))
        self.assertTrue(looks_exhausted(402, ""))
        self.assertTrue(looks_exhausted(200, "insufficient balance"))
        self.assertTrue(looks_exhausted(400, "usage limit reached"))
        # Sabotage: match on the status alone. A 400 carrying "insufficient
        # balance" is then read as a bad request we could fix by asking
        # differently, and the loop hammers a dead provider every iteration.
        self.assertFalse(looks_exhausted(400, "unknown field 'temperature'"))

    def test_an_exhausted_advisor_becomes_unavailable_and_recovers(self):
        from quantlab_manager.advisors import Advisor

        advisor = Advisor("h", "http://x", "m", "key", "sys")
        self.assertTrue(advisor.available)
        advisor.rest(1800)
        self.assertFalse(advisor.available)
        self.assertGreater(advisor.cooldown_remaining, 1700)
        advisor.rest(0)
        self.assertTrue(advisor.available)

    def test_the_loop_still_iterates_with_every_advisor_resting(self):
        """The whole point. Sabotage: raise when no advisor answers, and one
        exhausted provider stops a loop that was supposed to run for days."""
        from quantlab_manager.advisors import Advisor

        with tempfile.TemporaryDirectory() as directory:
            proposer = Advisor("p", "http://x", "m", "key", "sys")
            critic = Advisor("c", "http://x", "m", "key", "sys")
            proposer.rest(1800)
            critic.rest(1800)
            loop = ResearchLoop(
                lab_fit=None,
                lab_forward=None,
                store=None,
                symbols=["BTCUSDT"],
                repository=directory,
                proposer=proposer,
                critic=critic,
                state_path=Path(directory) / "state.json",
                ledger_path=Path(directory) / "l.jsonl",
            )
            outcome = loop.consult({"target_module": "BEAR", "why": "x"})
            self.assertEqual(outcome["seed_rules"], [])
            self.assertIn("resting", " ".join(outcome["advisors"].values()))


class TestNotGettingStuck(unittest.TestCase):
    """The rut that iterations 2-5 fell into, pinned from both sides.

    Two defects compounded. The gate compared a DETECTOR fit score against a
    BEAR one -- different sub-spaces with different pinned context, so a good
    score in one module locked every other module out by construction. And FRAME
    reads the last FORWARD run, which only updates when a fit clears the gate,
    so a loop that keeps missing re-reads the same run and re-picks the same
    module for ever.

    All sabotage-verified.
    """

    def _loop(self, directory, history, failures):
        loop = ResearchLoop(
            lab_fit=None,
            lab_forward=None,
            # `frame` falls back to scanning recorded runs when no forward run
            # has been pinned yet, so a store that answers `runs` is part of the
            # fixture rather than an optional extra.
            store=_Store({"backtest_id": "none"}, [], []),
            symbols=["BTCUSDT"],
            repository=directory,
            state_path=Path(directory) / "state.json",
            ledger_path=Path(directory) / "l.jsonl",
        )
        loop.state.history = history
        loop.state.consecutive_failures = failures
        return loop

    def test_a_stuck_loop_rotates_instead_of_re_reading_a_stale_diagnosis(self):
        """Sabotage: drop the rotation branch. FRAME then returns DETECTOR again
        because `last_forward_id` never changed, which is the observed rut."""
        with tempfile.TemporaryDirectory() as directory:
            history = [{"iteration": n, "module": "DETECTOR"} for n in range(2, 6)]
            frame = self._loop(directory, history, failures=4).frame()
            self.assertNotEqual(frame["target_module"], "DETECTOR")
            self.assertIn("stale", frame["why"])

    def test_it_rotates_to_something_the_recent_iterations_did_not_touch(self):
        with tempfile.TemporaryDirectory() as directory:
            history = [
                {"iteration": 2, "module": "DETECTOR"},
                {"iteration": 3, "module": "BEAR"},
                {"iteration": 4, "module": "SIDEWAYS"},
            ]
            frame = self._loop(directory, history, failures=3).frame()
            self.assertEqual(frame["target_module"], "BULL")

    def test_one_bad_iteration_does_not_trigger_rotation(self):
        """Rotation is for a rut, not for a single miss. Sabotage: rotate at
        `>= 1` and the loop abandons a module after one unlucky fit, which is
        how it stops going deep on anything."""
        with tempfile.TemporaryDirectory() as directory:
            loop = self._loop(directory, [{"iteration": 2, "module": "BEAR"}], 1)
            loop.state.last_forward_id = None
            frame = loop.frame()
            self.assertNotIn("stale", frame["why"])
            self.assertNotIn("Rotating", frame["why"])

    def test_the_gate_compares_a_module_against_its_own_history(self):
        """The deadlock, pinned. Sabotage: drop the `module` filter from the
        history scan. A BEAR score of +0.02 then becomes the bar every DETECTOR
        fit must clear, which no DETECTOR fit can reach by construction -- and
        that is exactly why iterations 2 through 5 all refused to open."""
        with tempfile.TemporaryDirectory() as directory:
            loop = self._loop(
                directory,
                [
                    {"iteration": 1, "module": "BEAR", "fit_score": 0.02},
                    {"iteration": 2, "module": "DETECTOR", "fit_score": -0.19},
                ],
                failures=1,
            )
            # A DETECTOR fit only has to beat DETECTOR's own -0.19.
            opens, best = loop.clears_gate("DETECTOR", -0.11)
            self.assertTrue(opens)
            self.assertEqual(best, -0.19)
            # BEAR still has to beat BEAR's +0.02.
            self.assertFalse(loop.clears_gate("BEAR", -0.11)[0])

    def test_a_module_with_no_history_opens_on_its_first_viable_fit(self):
        """Otherwise a module could never get its first measurement."""
        with tempfile.TemporaryDirectory() as directory:
            loop = self._loop(directory, [], failures=0)
            opens, best = loop.clears_gate("SIDEWAYS", -0.5)
            self.assertTrue(opens)
            self.assertIsNone(best)

    def test_a_rejected_fit_never_opens_the_forward_window(self):
        with tempfile.TemporaryDirectory() as directory:
            loop = self._loop(directory, [], failures=0)
            self.assertFalse(loop.clears_gate("BEAR", None)[0])
            self.assertFalse(loop.clears_gate("BEAR", float("-inf"))[0])
