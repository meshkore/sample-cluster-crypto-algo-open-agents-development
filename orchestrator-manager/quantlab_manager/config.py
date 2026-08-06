from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path("research/quantlab.db")
    research_root: Path = Path("research")
    data_root: Path = Path("data")
    seed: int = 42
    initial_equity: float = 10_000.0
    commission_bps: float = 10.0
    slippage_bps: float = 5.0
    funding_bps_per_bar: float = 0.0
    max_position_fraction: float = 1.0
    minimum_trades: int = 5
    portfolio: dict[str, Any] = field(default_factory=dict)
    universe: dict[str, Any] = field(default_factory=dict)
    autonomous: dict[str, Any] = field(default_factory=dict)
    scheduler_weights: dict[str, float] = field(default_factory=dict)
    splits: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path = "config/default.json") -> "Settings":
        raw: dict[str, Any] = json.loads(Path(path).read_text())
        for name in ("database_path", "research_root", "data_root"):
            raw[name] = Path(raw[name])
        weights = raw["scheduler_weights"]
        if abs(sum(weights.values()) - 1.0) > 1e-9 or any(
            v < 0 for v in weights.values()
        ):
            raise ValueError("scheduler_weights must be non-negative and sum to one")
        return cls(**raw)
