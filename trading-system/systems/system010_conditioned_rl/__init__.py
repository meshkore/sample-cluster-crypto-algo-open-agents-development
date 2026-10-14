"""System 10 - market gate + AI selector + AI exit with signal-strength sizing.

Read `research/system10/README.md` first: what runs, the current release, and the decision
log of what was tried and closed. Design: `.meshkore/context/system10-design.md`. The package
name is historical; the reinforcement-learning lines it started with were retired on
2026-10-14 (git tag `s10-before-cleanup`).

Lineage: system 06 (declared in `check_layering.py`) - its dataset, features and breadth
channel. The registered brain abstains; the system trades through `paper.py`'s book.
"""

from __future__ import annotations

__all__ = ["ConditionedPolicyBrain"]

from .strategy import ConditionedPolicyBrain  # noqa: F401 -- registers "system10-conditioned-rl"
