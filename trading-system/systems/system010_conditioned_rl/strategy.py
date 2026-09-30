"""The system 10 brain: consult the policy inside the region, abstain outside it.

This is the surface the rest of the laboratory already knows — `decide(tick)` returning a
`Decision` — and it is deliberately thin. Everything interesting is in three places:

    region.py   R(t): the causal predicate that says whether this bar is in the region
    policy.py   pi(a | s): what to do, given the market AND the book
    env.py      where the policy is trained, which is the frozen backtester's ledger

**Until a policy is exported this brain abstains and says so.** That is not a placeholder
left by accident: system 004 is on record producing +495% in training and -5.81% on the
sealed year, and the way a half-built system does damage in this laboratory is by producing
a number that enters the record. An abstaining brain is honest and costs nothing; a brain
that trades on an untrained policy is a result waiting to be cited.

The shape of the decision is the one the live layer and the backtester share, so a package
exported by `export.py` can be dropped into `live-trading/engines/` with no adapter:

    tick     = {"timestamp": ..., "candles": {symbol: bar}, "account": {...}}
    decision = Decision(orders=[{symbol, side, notional, reason, rationale}], note=...)
"""

from __future__ import annotations

from typing import Any

from quantlab_core.brains import register
from quantlab_core.runner import Decision


@register(
    "system10-conditioned-rl",
    "A policy trained by reinforcement only inside the causal region where the oracle's "
    "best trades occur, rewarded by profit against drawdown after costs; abstains outside "
    "the region and until a policy is exported.",
)
class ConditionedPolicyBrain:
    """Long-only spot. Three slots. Consulted inside the region, exits managed outside it.

    Parameters mirror the design's section 4 so that a configuration is readable as the
    thing the design argues about, not as a bag of numbers:

    `policy` is the exported policy directory (weights + the action head). `region` is the
    exported predicate. Both `None` means "not trained yet", which is the state this system
    ships in and the state in which it abstains.
    """

    def __init__(
        self,
        policy: str | None = None,        # exported policy directory; None = abstain
        region: str | None = None,        # exported region predicate; None = abstain
        max_positions: int = 3,           # the book the region's coverage is priced against
        position_fraction: float = 0.3333,
        half_slot: float = 0.5,           # the "enter half" action, as a fraction of a slot
        lambda_drawdown: float = 1.0,     # reward shaping, carried for provenance only
        exit_rule: str = "system06",      # how positions are managed OUTSIDE the region
    ) -> None:
        self.policy_path = policy
        self.region_path = region
        self.max_positions = int(max_positions)
        self.position_fraction = float(position_fraction)
        self.half_slot = float(half_slot)
        self.lambda_drawdown = float(lambda_drawdown)
        self.exit_rule = exit_rule
        self._policy: Any = None
        self._region: Any = None

    def parameters(self) -> dict[str, Any]:
        """What the monitor's model card and the backtest fingerprint record."""
        return {
            "policy": self.policy_path,
            "region": self.region_path,
            "max_positions": self.max_positions,
            "position_fraction": self.position_fraction,
            "half_slot": self.half_slot,
            "lambda_drawdown": self.lambda_drawdown,
            "exit_rule": self.exit_rule,
            "trained": self.trained,
        }

    @property
    def trained(self) -> bool:
        return bool(self.policy_path and self.region_path)

    def decide(self, tick: dict[str, Any]) -> Decision:
        if not self.trained:
            # The whole system, honestly, in one line of behaviour.
            return Decision(note="system10: no policy exported yet - abstaining")
        raise NotImplementedError(
            "S10-8 trains the policy and S10-12 wires this adapter. Until then this brain "
            "abstains rather than guessing; see .meshkore/context/system10-design.md."
        )
