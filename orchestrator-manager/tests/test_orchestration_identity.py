"""A run's identity must contain everything that makes it that run.

`backtest_id` is derived, not random, so two configurations that differ in any
decision must not collide -- the second silently overwrites the first. This file
exists because they did: the four-module system run once on a ratchet drawdown
basis and once on a peak basis produced the same id, because the orchestrator
passed `policy={}` unconditionally.

All sabotage-verified.
"""

from dataclasses import dataclass
import unittest

from quantlab_backtester.ledger import BacktestRun
from quantlab_manager.orchestration import _describe, _policy_of


@dataclass(frozen=True)
class _Policy:
    maximum_drawdown: float = 0.30
    drawdown_basis: str = "peak"


class _Publishing:
    def __init__(self, **params):
        self.policy = _Policy(**params.pop("policy", {}))
        self._params = params

    def parameters(self):
        return dict(self._params)


class _Plain:
    def __init__(self):
        self.fast_period = 50
        self.label = "plain"
        self.ignored = [1, 2, 3]


class TestDescribe(unittest.TestCase):
    def test_a_brain_that_publishes_parameters_is_taken_at_its_word(self):
        described = _describe(_Publishing(regime_scope="asset", bull_weight=1.0))
        self.assertEqual(described, {"regime_scope": "asset", "bull_weight": 1.0})

    def test_a_brain_without_parameters_falls_back_to_its_scalars(self):
        described = _describe(_Plain())
        self.assertEqual(described, {"fast_period": 50, "label": "plain"})

    def test_the_policy_is_read_off_the_brain(self):
        self.assertEqual(
            _policy_of(_Publishing(policy={"drawdown_basis": "ratchet"})),
            {"maximum_drawdown": 0.30, "drawdown_basis": "ratchet"},
        )

    def test_a_brain_with_no_policy_contributes_nothing(self):
        self.assertEqual(_policy_of(_Plain()), {})


class TestIdentity(unittest.TestCase):
    def _fingerprint(self, brain):
        return BacktestRun.fingerprint(
            "four-module",
            _describe(brain),
            _policy_of(brain),
            ["BTCUSDT", "ETHUSDT"],
            "2018-01-01",
            "2025-12-31",
            100_000.0,
        )

    def test_two_drawdown_bases_are_two_different_runs(self):
        """The bug, pinned. Sabotage: return `{}` from `_policy_of`. Both
        configurations then produce one id and the second overwrites the first."""
        peak = self._fingerprint(_Publishing(policy={"drawdown_basis": "peak"}))
        ratchet = self._fingerprint(_Publishing(policy={"drawdown_basis": "ratchet"}))
        self.assertNotEqual(peak, ratchet)

    def test_the_same_configuration_still_collides_on_purpose(self):
        """A reproduction is information, so identical inputs must share an id."""
        self.assertEqual(
            self._fingerprint(_Publishing(regime_scope="market")),
            self._fingerprint(_Publishing(regime_scope="market")),
        )

    def test_the_regime_scope_changes_the_identity(self):
        self.assertNotEqual(
            self._fingerprint(_Publishing(regime_scope="market")),
            self._fingerprint(_Publishing(regime_scope="asset")),
        )


if __name__ == "__main__":
    unittest.main()
