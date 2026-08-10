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
        for module in ("BULL", "SIDEWAYS", "BEAR", "DETECTOR", "POLICY"):
            self.assertIn(module, MODULE_KEYS)

    def test_the_whole_search_space_is_reachable_by_some_module(self):
        """The gap that ran for 58 iterations. Sizing, stops and the mandate are
        the trading system's hypothesis -- CONTRACT.md puts them in the
        hypothesis space -- and no iteration could reach one of them, while the
        champion ran at 3.1% average exposure and 7.65% time in market.

        Sabotage: drop the POLICY entry from MODULE_KEYS and seven dimensions
        become unreachable again.
        """
        from quantlab_trading.regime_system import FourModuleBrain

        every = {d.name for d in FourModuleBrain.search_space().dimensions}
        reachable = set()
        for module in MODULE_KEYS:
            space, _ = module_space(module)
            reachable |= {d.name for d in space.dimensions}

        self.assertEqual(
            every - reachable, set(), "dimensions no iteration can ever move"
        )

    def test_policy_moves_money_management_and_nothing_else(self):
        space, slots = module_space("POLICY")
        names = {d.name for d in space.dimensions}
        self.assertEqual(slots, (), "policy has no rule trees to evolve")
        self.assertIn("stop_loss_pct", names)
        self.assertIn("take_profit_pct", names)
        self.assertIn("risk_per_trade", names)
        # it must not reach into a branch's rules -- that is the other modules'
        # job, and an iteration that moves both attributes nothing
        self.assertFalse(
            any(n.startswith(("bull_", "bear_", "sideways_")) for n in names)
        )

    def test_the_detector_can_change_how_a_symbol_gets_its_regime(self):
        """`regime_scope` was in the search space and reachable by nobody. At
        market scope every bar of 2026 classifies BEAR, so the risers the ledger
        records -- 40 of 399 up, several above +100% -- cannot be traded by
        construction."""
        space, _ = module_space("DETECTOR")
        self.assertIn("regime_scope", {d.name for d in space.dimensions})


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
            (Path(directory) / "CONTRACT.md").write_text("x")
            self.assertEqual(self._loop(directory).tried(), {"deadbeef"})

    def test_a_corrupt_ledger_line_does_not_stop_the_loop(self):
        """Re-running dead ideas is the only way a loop like this fails, but so
        is refusing to start because one line is malformed."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
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
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory)
            loop.state.iteration = 7
            loop.state.incumbent = {"bear_weight": 0.4}
            loop.state.incumbent_forward = 0.02
            loop._save()
            restored = LoopState.load(loop.state_path)
            self.assertEqual(restored.iteration, 7)
            self.assertEqual(restored.incumbent, {"bear_weight": 0.4})
            self.assertEqual(restored.incumbent_forward, 0.02)


class TestTheDeploymentScopeIsPinned(unittest.TestCase):
    """Where the system is deployed is not part of the hypothesis space.

    The universe reached the brain through nothing for sixty-six iterations,
    and the fix is only a fix if it reaches BOTH the fit and the single forward
    shot -- fitting under one liquidity floor and forwarding under another
    would make the two numbers unrelated.
    """

    DEPLOYMENT = {"minimum_daily_quote_volume": 10_000_000.0, "tradeable_assets": 100}

    def _loop(self, directory, incumbent=None):
        loop = ResearchLoop(
            lab_fit=None,
            lab_forward=_RecordingLab(),
            store=None,
            symbols=["BTCUSDT"],
            repository=directory,
            state_path=Path(directory) / "state.json",
            ledger_path=Path(directory) / "hypotheses.jsonl",
            deployment=dict(self.DEPLOYMENT),
        )
        loop.state.incumbent = dict(incumbent or {})
        return loop

    def test_the_forward_shot_carries_it(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory)
            loop.forward({"bear_weight": 0.5}, "BEAR")
            sent = loop.lab_forward.calls[-1]["parameters"]
            self.assertEqual(sent["minimum_daily_quote_volume"], 10_000_000.0)
            self.assertEqual(sent["tradeable_assets"], 100)

    def test_it_overrides_an_incumbent_from_another_scope(self):
        """An incumbent recorded under the old universe must not drag the old
        universe forward into the new one. Sabotage: put `**self.deployment`
        BEFORE `**self.state.incumbent` and this is what catches it."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, incumbent={"minimum_daily_quote_volume": 0.0})
            loop.forward({}, "BEAR")
            sent = loop.lab_forward.calls[-1]["parameters"]
            self.assertEqual(sent["minimum_daily_quote_volume"], 10_000_000.0)

    def test_no_module_can_reach_it(self):
        for module, keys in MODULE_KEYS.items():
            self.assertNotIn("minimum_daily_quote_volume", keys, module)
            self.assertNotIn("tradeable_assets", keys, module)


class _RecordingLab:
    """Enough of an Orchestrator to see what a launch was asked to run."""

    def __init__(self):
        self.calls = []

    def launch(self, strategy, **kwargs):
        self.calls.append({"strategy": strategy, **kwargs})
        return {"backtest_id": "x", "summary": {"status": "complete"}}


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
        # Dropped, but no longer silently: "the model proposed nothing" and
        # "the grammar refused everything it proposed" were the same
        # observation from outside, and a guard shipped this morning was too
        # broad by exactly one pair with nothing able to show it.
        self.assertEqual(len(proposal["rejected_rules"]), 2)
        self.assertTrue(any("moon_phase" in r for r in proposal["rejected_rules"]))

    def test_a_proposal_the_grammar_fully_accepts_reports_no_rejections(self):
        proposal = validate_proposal(
            {
                "module": "bear",
                "claim": "c",
                "seed_rules": [
                    {
                        "t": "gt",
                        "a": {"t": "px", "name": "close"},
                        "b": {"t": "px", "name": "open"},
                    }
                ],
            }
        )
        self.assertEqual(len(proposal["seed_rules"]), 1, "an up candle is a signal")
        self.assertEqual(proposal["rejected_rules"], [])

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
            # `rejected_rules` is written by the validator, never by the model:
            # it is what the grammar refused, not something a proposal can set.
            {
                "module",
                "claim",
                "kill_condition",
                "reasoning",
                "seed_rules",
                "rejected_rules",
            },
        )
        self.assertNotIn("shell", proposal)

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
            (Path(directory) / "CONTRACT.md").write_text("x")
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


class TestTheAdvisorsKnowWhatSystemThisIs(unittest.TestCase):
    """The proposer reasoned its way to a short in a system that cannot short.

    On iteration 58 it proposed "sourcing BEAR shorts from failing rallies",
    entering on a cross_down of close through sma_20 and "covering into
    oversold". Nothing in its system prompt or its briefing said the system is
    long only, so its entry would have been executed as a BUY into a
    rolling-over rally -- the failed-bounce trade H-REGIME-001 already measured
    at -8.46%. The rule was syntactically valid and the reasoning behind it was
    inverted, which is the worst combination: it passes every check.
    """

    def test_the_proposer_can_answer_about_every_module_the_loop_targets(self):
        """POLICY was added to the rotation and left out of the validator's
        allow-list, so every proposal for a POLICY iteration was discarded whole
        and the schema told the model the module did not exist. The loop was
        working on money management with its advisor blind to it.

        Sabotage: drop POLICY from VALID_MODULES and this fails.
        """
        from quantlab_manager.advisors import PROPOSER_SYSTEM, VALID_MODULES
        from quantlab_manager.loop import MODULE_KEYS

        self.assertEqual(set(VALID_MODULES), set(MODULE_KEYS))
        for module in MODULE_KEYS:
            self.assertIn(module, PROPOSER_SYSTEM, f"{module} unknown to the proposer")
            self.assertIsNotNone(
                validate_proposal({"module": module, "claim": "c"}),
                f"a {module} proposal is discarded",
            )

    def test_a_claim_about_another_module_is_not_this_iteration_s_hypothesis(self):
        """The ledger's `statement` is what the run is recorded as having tried.
        A POLICY iteration that adopted a BEAR claim would describe something
        that did not happen.

        Sabotage: adopt the claim regardless of module and this fails.
        """
        from quantlab_manager.loop import statement_for

        bear = {"module": "BEAR", "claim": "a bear rule will do X"}
        self.assertEqual(statement_for("BEAR", bear), "a bear rule will do X")
        self.assertNotIn("bear rule will do X", statement_for("POLICY", bear))
        self.assertIn("POLICY", statement_for("POLICY", bear))

    def test_the_fallback_does_not_claim_rules_a_module_does_not_have(self):
        """DETECTOR and POLICY evolve no rule trees. Saying they do is a false
        sentence in a record whose only job is to be true."""
        from quantlab_manager.loop import statement_for

        for module in ("POLICY", "DETECTOR"):
            self.assertNotIn("entry and exit rules", statement_for(module, None))
        for module in ("BEAR", "BULL", "SIDEWAYS"):
            self.assertIn("entry and exit rules", statement_for(module, None))

    def test_the_proposer_is_told_the_system_is_long_only(self):
        from quantlab_manager.advisors import PROPOSER_SYSTEM

        self.assertIn("LONG ONLY", PROPOSER_SYSTEM)
        self.assertIn("BUY", PROPOSER_SYSTEM)

    def test_the_critic_can_refute_a_proposal_reasoned_as_a_short(self):
        from quantlab_manager.advisors import CRITIC_SYSTEM

        self.assertIn("LONG ONLY", CRITIC_SYSTEM)
        self.assertIn("SHORT", CRITIC_SYSTEM)

    def test_the_cluster_is_read_before_the_proposal_not_after_it(self):
        """Every reply this project ever received was archived and read by
        nobody: `consult()` read the cluster after the proposal was formed, and
        the briefing never carried `peers` at all. Asking for ideas and then not
        reading them until afterwards is broadcasting, not collaborating.

        Sabotage: move the read back below the proposer and the briefing the
        proposer sees has no peer replies in it.
        """
        seen = {}

        class _Cluster:
            enabled = True

            def post(self, handle, body):
                return True

            def read(self, seconds=0):
                return ["a peer suggests testing regime_scope=asset"]

        class _Proposer:
            available = True
            handle = "p"
            cooling = False
            last_error = None

            def ask(self, briefing):
                seen["briefing"] = briefing
                return None

        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = ResearchLoop(
                lab_fit=None,
                lab_forward=None,
                store=_Store({"backtest_id": "none"}, [], []),
                symbols=["BTCUSDT"],
                repository=directory,
                cluster=_Cluster(),
                proposer=_Proposer(),
                state_path=Path(directory) / "state.json",
                ledger_path=Path(directory) / "l.jsonl",
            )
            out = loop.consult({"target_module": "BEAR", "why": "because"})

        self.assertIn("briefing", seen, "the proposer was never asked")
        payload = json.loads(seen["briefing"])
        self.assertIn("peer_replies", payload)
        self.assertEqual(len(payload["peer_replies"]), 1)
        self.assertIn("regime_scope", payload["peer_replies"][0])
        self.assertEqual(len(out["peers"]), 1, "the reply is still recorded")

    def test_the_briefing_carries_it_as_evidence_not_only_as_instruction(self):
        """A system prompt is one message and the briefing is the thing the
        model actually reasons over, so the fact belongs in both."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = ResearchLoop(
                lab_fit=None,
                lab_forward=None,
                store=_Store({"backtest_id": "none"}, [], []),
                symbols=["BTCUSDT"],
                repository=directory,
                state_path=Path(directory) / "state.json",
                ledger_path=Path(directory) / "l.jsonl",
            )
            briefing = loop._briefing({"target_module": "BEAR", "why": "because"})

        payload = json.loads(briefing)
        self.assertIn("position_direction", payload)
        self.assertIn("LONG ONLY", payload["position_direction"])
        self.assertIn("cannot short", payload["position_direction"])


class TestWhatTheLedgerMayClaim(unittest.TestCase):
    """A hypothesis that was never tested is not a hypothesis that failed.

    H-L053 moved the bear module and returned +1.12% on 96 trades. H-L057 moved
    the SIDEWAYS module and returned +1.12% on 96 trades -- the same number to
    four decimals, from a different fit, because attribution shows all 96 of
    those trades belonged to BEAR. The sideways module never fired in 2026, so
    the run re-measured the incumbent. It was recorded REFUTED, which claims
    2026 rejected a sideways idea it never saw.
    """

    def test_a_module_that_never_traded_was_not_tested(self):
        from quantlab_manager.loop import tested_the_module

        attribution = {"BEAR": {"trades": 96, "pnl": 5523.0}}
        self.assertTrue(tested_the_module("BEAR", attribution))
        self.assertFalse(tested_the_module("SIDEWAYS", attribution))
        self.assertFalse(tested_the_module("BULL", attribution))

    def test_a_module_present_but_idle_was_not_tested(self):
        from quantlab_manager.loop import tested_the_module

        self.assertFalse(tested_the_module("SIDEWAYS", {"SIDEWAYS": {"trades": 0}}))

    def test_the_detector_is_exempt_because_it_takes_no_trades(self):
        """It decides which module trades, so its effect is the MIX of the
        others. Requiring a DETECTOR key would make every detector iteration
        permanently untestable."""
        from quantlab_manager.loop import tested_the_module

        self.assertTrue(tested_the_module("DETECTOR", {"BEAR": {"trades": 96}}))
        self.assertTrue(tested_the_module("DETECTOR", {}))

    def test_missing_attribution_is_not_read_as_success(self):
        from quantlab_manager.loop import tested_the_module

        self.assertFalse(tested_the_module("BEAR", None))
        self.assertFalse(tested_the_module("BEAR", {}))

    def test_an_untested_hypothesis_is_inconclusive_not_refuted(self):
        """Spending a refutation on nothing tells the next contributor a
        direction is dead when nobody has been down it."""
        from quantlab_manager.loop import verdict_of

        self.assertEqual(
            verdict_of(traded=True, acted=False, improved=False), "INCONCLUSIVE"
        )
        self.assertEqual(verdict_of(traded=True, acted=True, improved=False), "REFUTED")
        self.assertEqual(
            verdict_of(traded=True, acted=True, improved=True), "CONFIRMED"
        )

    def test_standing_aside_is_still_a_refutation(self):
        """A configuration that took no trades at all HAS been tested: standing
        aside is what it does. Every such run in the ledger says REFUTED and
        this must not silently reclassify them."""
        from quantlab_manager.loop import verdict_of

        self.assertEqual(
            verdict_of(traded=False, acted=False, improved=False), "REFUTED"
        )


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

    def test_a_forward_run_that_fails_still_leaves_a_ledger_record(self):
        """H-L069 is the hole this closes.

        The loop framed POLICY, consulted, fitted for thirty minutes, announced
        that 2026 was opening -- and then lost the entire iteration to
        `TimeoutError` on POST /sessions. No record, no id, and a ledger that
        skips from H-L068U to H-L070 without saying why. A fit that raises has
        been recorded ABANDONED since the loop was written; a forward that
        raised was not.

        Sabotage: remove the try/except around `self.forward(...)`. The
        exception then escapes `iterate()` and this test errors instead of
        failing -- which is precisely the shape of the silent gap.
        """
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, [], failures=0)
            loop.consult = lambda frame: {
                "seed_rules": [],
                "peers": [],
                "advisors": {},
                "proposal": None,
                "critique": None,
            }
            loop.fit = lambda module, seeds: {
                "genome": {"risk_per_trade": 0.02},
                "score": {
                    "value": 0.1,
                    "returns": (0.1,),
                    "drawdowns": (0.1,),
                    "trades": 100,
                },
                "evaluations": 10,
                "seed": 1,
            }

            def timed_out(genome, module):
                raise TimeoutError("timed out")

            loop.forward = timed_out

            record = loop.iterate()

            self.assertEqual(record["verdict"], "ABANDONED")
            self.assertIn("TimeoutError", record["notes"])
            # The window was announced but never actually served, so it is not
            # spent and the hypothesis may be tried again.
            self.assertFalse(record["opened_2026"])
            self.assertIn("NOT spent", record["notes"])
            self.assertEqual(loop.state.consecutive_failures, 1)

            written = [
                json.loads(line)
                for line in loop.ledger_path.read_text().splitlines()
                if line.strip()
            ]
            self.assertEqual(written[-1]["id"], record["id"])

    def test_a_stuck_loop_rotates_instead_of_re_reading_a_stale_diagnosis(self):
        """Sabotage: drop the rotation branch. FRAME then returns DETECTOR again
        because `last_forward_id` never changed, which is the observed rut."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            history = [{"iteration": n, "module": "DETECTOR"} for n in range(2, 6)]
            frame = self._loop(directory, history, failures=4).frame()
            self.assertNotEqual(frame["target_module"], "DETECTOR")
            self.assertIn("stale", frame["why"])

    def test_it_rotates_to_something_the_recent_iterations_did_not_touch(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            recent = ["DETECTOR", "BEAR", "SIDEWAYS"]
            history = [
                {"iteration": n, "module": m} for n, m in enumerate(recent, start=2)
            ]
            loop = self._loop(directory, history, failures=3)
            frame = loop.frame()

            self.assertNotIn(frame["target_module"], recent)
            # the first untouched module in rotation order, not just any of them
            self.assertEqual(
                frame["target_module"],
                next(m for m in loop.ROTATION if m not in recent),
            )

    def test_rotation_reaches_the_modules_the_diagnosis_never_can(self):
        """The diagnosis can only name a branch that traded, so POLICY and
        DETECTOR are unreachable from it and rotation is their only turn. They
        come before BULL and SIDEWAYS because every bar of the forward window
        classifies BEAR, so those two cannot produce forward evidence at all."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, [], failures=0)
            self.assertIn("POLICY", loop.ROTATION)
            self.assertLess(loop.ROTATION.index("POLICY"), loop.ROTATION.index("BULL"))
            self.assertLess(
                loop.ROTATION.index("DETECTOR"), loop.ROTATION.index("SIDEWAYS")
            )

    def test_one_bad_iteration_does_not_trigger_rotation(self):
        """Rotation is for a rut, not for a single miss. Sabotage: rotate at
        `>= 1` and the loop abandons a module after one unlucky fit, which is
        how it stops going deep on anything."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, [{"iteration": 2, "module": "BEAR"}], 1)
            loop.state.last_forward_id = None
            frame = loop.frame()
            self.assertNotIn("stale", frame["why"])
            self.assertNotIn("Rotating", frame["why"])

    def test_a_new_deployment_scope_re_calibrates_sizing_first(self):
        """Measured on iteration 69, the first under the widened universe.

        Nine complete candidates were evaluated and all nine were rejected by
        the 30% mandate, because the incumbent's sizing was fitted against a
        20-name book and the new one holds 54. A BEAR search may only move
        `bear_*` dimensions, so it cannot reach a single sizing knob and every
        iteration it runs can only produce another rejection.

        Sabotage: drop this branch. `frame()` then diagnoses off a forward run
        from the OLD universe and targets whatever that run's attribution
        says -- which is how the loop spent iteration 69 on BEAR.
        """
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, [], failures=0)
            loop.state.history = []
            self.assertEqual(loop.frame()["target_module"], "POLICY")

    def test_once_this_scope_has_history_the_diagnosis_takes_over_again(self):
        """It is a re-calibration, not a permanent preference for POLICY."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, [], failures=0)
            loop.state.history = [
                {
                    "iteration": 1,
                    "module": "POLICY",
                    "fit_score": -0.1,
                    "folds": loop.fold_signature(),
                }
            ]
            self.assertNotEqual(loop.frame()["target_module"], "POLICY")

    def test_a_score_from_another_universe_is_not_a_bar_to_clear(self):
        """Every score in the ledger was measured on an alphabetical 55.

        None of them is a fact about the universe the loop trades now, and the
        gate must not treat them as one -- otherwise the first iteration under
        the new universe is judged against a number from the old one and the
        forward window is spent, or withheld, for no reason at all.

        Sabotage: drop the symbol count from `fold_signature`. The stale score
        below then becomes the bar, and `opens` goes False.
        """
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, [], failures=1)
            loop.symbols = ["AAAUSDT"] * 386
            loop.state.history = [
                {
                    "iteration": 1,
                    "module": "BEAR",
                    "fit_score": 0.99,
                    # measured on 55 symbols, under no liquidity floor
                    "folds": "2018-01-01:2025-12-31:4|55",
                }
            ]
            opens, best = loop.clears_gate("BEAR", -0.5)
            self.assertTrue(opens, "judged against a score from another universe")
            self.assertIsNone(best)

    def test_the_gate_compares_a_module_against_its_own_history(self):
        """The deadlock, pinned. Sabotage: drop the `module` filter from the
        history scan. A BEAR score of +0.02 then becomes the bar every DETECTOR
        fit must clear, which no DETECTOR fit can reach by construction -- and
        that is exactly why iterations 2 through 5 all refused to open."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, [], failures=1)
            here = loop.fold_signature()
            loop.state.history = [
                {"iteration": 1, "module": "BEAR", "fit_score": 0.02, "folds": here},
                {
                    "iteration": 2,
                    "module": "DETECTOR",
                    "fit_score": -0.19,
                    "folds": here,
                },
            ]
            # A DETECTOR fit only has to beat DETECTOR's own -0.19.
            opens, best = loop.clears_gate("DETECTOR", -0.11)
            self.assertTrue(opens)
            self.assertEqual(best, -0.19)
            # BEAR still has to beat BEAR's +0.02.
            self.assertFalse(loop.clears_gate("BEAR", -0.11)[0])

    def test_a_module_with_no_history_opens_on_its_first_viable_fit(self):
        """Otherwise a module could never get its first measurement."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, [], failures=0)
            opens, best = loop.clears_gate("SIDEWAYS", -0.5)
            self.assertTrue(opens)
            self.assertIsNone(best)

    def test_a_rejected_fit_never_opens_the_forward_window(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, [], failures=0)
            self.assertFalse(loop.clears_gate("BEAR", None)[0])
            self.assertFalse(loop.clears_gate("BEAR", float("-inf"))[0])

    def test_a_score_from_a_different_fold_set_is_not_the_bar(self):
        """The sixteen-iteration deadlock, pinned.

        `H-L001` was measured on three folds; every fit after it used four, over
        different windows and therefore different data. Its +0.0209 became
        BEAR's permanent high-water mark, and BEAR -- the module the loop's own
        diagnosis names as the one that is losing -- did not open the forward
        window once in sixteen attempts while every other module did.

        Sabotage: drop the `folds` filter and the three-fold score locks the
        module out again.
        """
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, [], failures=0)
            loop.state.history = [
                # measured on three folds: a different measurement entirely
                {
                    "iteration": 1,
                    "module": "BEAR",
                    "fit_score": 0.0209,
                    "folds": "2018-01-01:2025-12-31:3",
                },
                {
                    "iteration": 32,
                    "module": "BEAR",
                    "fit_score": -0.1008,
                    "folds": loop.fold_signature(),
                },
            ]
            opens, best = loop.clears_gate("BEAR", -0.1008)
            self.assertTrue(opens)
            self.assertEqual(best, -0.1008)

    def test_a_module_whose_only_history_is_incomparable_opens(self):
        """Same rule as a module with no history at all: it cannot be asked to
        beat a number that was never measured on the same thing."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, [], failures=0)
            loop.state.history = [
                {
                    "iteration": 1,
                    "module": "BEAR",
                    "fit_score": 0.0209,
                    "folds": "2018-01-01:2025-12-31:3",
                }
            ]
            opens, best = loop.clears_gate("BEAR", -0.5)
            self.assertTrue(opens)
            self.assertIsNone(best)

    def test_the_gate_does_not_depend_on_when_the_process_last_restarted(self):
        """`document()` trimmed the history to forty entries but the append did
        not, so a long-lived process gated against iterations a restarted one
        could not see. The bear module was refused against a score from
        iteration 1 that no reloaded state contained.

        Sabotage: remove the trim from the append and the two disagree.
        """
        from quantlab_manager.loop import HISTORY_LIMIT, LoopState

        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            loop = self._loop(directory, [], failures=0)
            # Run past the bound the way the loop does: one entry per iteration.
            for n in range(1, HISTORY_LIMIT + 20):
                loop._remember({"iteration": n, "module": "BEAR", "fit_score": -0.1})
            loop._save()

            reloaded = LoopState.load(Path(directory) / "state.json")
            self.assertEqual(len(loop.state.history), HISTORY_LIMIT)
            self.assertEqual(
                [h["iteration"] for h in loop.state.history],
                [h["iteration"] for h in reloaded.history],
                "the running process gated against iterations a restart cannot see",
            )
            # and iteration 1 -- the three-fold outlier -- is genuinely gone
            self.assertNotIn(1, [h["iteration"] for h in loop.state.history])


class TestResumingIsNeverSilent(unittest.TestCase):
    """A loop that cannot read its state must stop, not start again at zero.

    Found in production: under launchd the loop could not read the repository
    under ~/Documents, `load` swallowed the PermissionError, and it began
    iteration 1 on top of a ledger holding seventy-eight records. The next
    write would have put a second H-L001 into an append-only file.
    """

    def test_a_missing_state_is_a_first_run(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            state = LoopState.load(Path(directory) / "absent.json")
            self.assertEqual(state.iteration, 0)

    def test_a_state_that_cannot_be_read_stops_the_loop(self):
        """Sabotage: catch OSError and return `cls()`. That is the bug."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            path = Path(directory) / "loop-state.json"
            path.write_text(json.dumps({"iteration": 78}))
            path.chmod(0o000)
            try:
                with self.assertRaises(RuntimeError) as caught:
                    LoopState.load(path)
                self.assertIn("Refusing to start", str(caught.exception))
            finally:
                path.chmod(0o600)

    def test_a_corrupt_state_stops_the_loop_too(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            path = Path(directory) / "loop-state.json"
            path.write_text("{not json")
            with self.assertRaises(RuntimeError):
                LoopState.load(path)

    def test_a_readable_state_still_resumes(self):
        """OPEN-GATE CONTROL: without this the tests above pass if load always
        raises."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            path = Path(directory) / "loop-state.json"
            path.write_text(json.dumps({"iteration": 78, "incumbent_forward": 0.002}))
            state = LoopState.load(path)
            self.assertEqual(state.iteration, 78)
            self.assertAlmostEqual(state.incumbent_forward, 0.002)


class TestItRefusesARepositoryItCannotSee(unittest.TestCase):
    """macOS hides ~/Documents from background agents rather than denying it.

    So the state file raised FileNotFoundError, which is indistinguishable from
    a fresh checkout, and the supervised loop began iteration 1 on top of a
    ledger holding seventy-eight records. A marker that cannot be absent from a
    real checkout is what tells the two apart.
    """

    def _loop(self, repository):
        return ResearchLoop(
            lab_fit=None,
            lab_forward=None,
            store=None,
            symbols=["BTCUSDT"],
            repository=repository,
        )

    def test_it_refuses_a_repository_with_no_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            # deliberately NOT a checkout: no CONTRACT.md
            with self.assertRaises(RuntimeError) as caught:
                self._loop(directory)
            self.assertIn("CONTRACT.md", str(caught.exception))

    def test_a_real_checkout_starts(self):
        """OPEN-GATE CONTROL. Without it the check above passes if the loop
        refuses to start anywhere at all."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "CONTRACT.md").write_text("x")
            root = Path(directory)
            (root / "CONTRACT.md").write_text("the instrument is frozen\n")
            loop = self._loop(root)
            self.assertEqual(loop.state.iteration, 0)
