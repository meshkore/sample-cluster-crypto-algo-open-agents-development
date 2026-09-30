"""System 10 — the conditioned policy: reinforcement learning where the best trades live.

The hypothesis in one sentence: the best trades in this market do not happen everywhere,
they cluster under a small set of causal conditions, so a policy should be *trained and
consulted* only inside that region — and rewarded by the operator's own criterion, profit
against drawdown after costs, rather than by a proxy.

The plan this package implements is `.meshkore/context/system10-design.md`. Read it before
changing anything here: it carries the defaults with their reasons, the laboratory's
standing conditions, and the kill conditions that stop the system rather than letting it
drift.

Lineage: system 06 (declared in `check_layering.py`). 010 reuses 06's dataset, its zigzag
oracle and its causal channels — the expensive, already-paid-for parts — and adds the three
things 06 does not have: a region, a policy that sees the BOOK as well as the market, and a
reward that is the ranking criterion itself.

The brain registers on import, so a fresh process can find it. **It abstains** until a
policy has been exported: an unfinished system that trades is worse than one that does not
exist, because its numbers enter the record.
"""

from __future__ import annotations

__all__ = ["ConditionedPolicyBrain"]

from .strategy import ConditionedPolicyBrain  # noqa: F401 -- registers "system10-conditioned-rl"
