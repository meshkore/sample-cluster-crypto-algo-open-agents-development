"""The system 10 brain, registered with the laboratory's brain registry - and abstaining.

System 10 trades through its own book (`research/system10/tools/conditions.py`), run on
live bars by `paper.py`; it has no per-tick `decide()` path. The registration is kept so the
registry knows the system; it abstains rather than guess (tests/test_system010_abstains.py).
"""

from __future__ import annotations

from typing import Any

from quantlab_core.brains import register
from quantlab_core.runner import Decision


@register(
    "system10-conditioned-rl",
    "System 10: market gate + AI selector + AI exit with signal-strength sizing, chosen by a "
    "walk-forward condition search; traded through its own book (paper.py), so this "
    "per-tick brain abstains.",
)
class ConditionedPolicyBrain:
    """Abstains on every tick. The name is historical (the system no longer uses RL)."""

    def parameters(self) -> dict[str, Any]:
        return {"trained": False, "path": "research/system10/paper (paper.py)"}

    @property
    def trained(self) -> bool:
        return False

    def decide(self, tick: dict[str, Any]) -> Decision:
        return Decision(note="system10: trades through paper.py's book - this brain abstains")
