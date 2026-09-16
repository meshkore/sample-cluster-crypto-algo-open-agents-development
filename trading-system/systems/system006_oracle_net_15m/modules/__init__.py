"""Decision modules for the system 06 ensemble.

Each module has one job, holds only its own state, and is combined by
`system006_oracle_net_15m.orchestrator.EnsembleBrain`. See `../REFACTOR_PLAN.md` for the
architecture and the module contract in `base.py`.
"""

from __future__ import annotations

from .base import MarketView, Module, ModuleOutput, SymbolVote

__all__ = ["MarketView", "Module", "ModuleOutput", "SymbolVote"]
