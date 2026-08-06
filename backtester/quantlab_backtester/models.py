from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ResearchState(str, Enum):
    OBSERVE = "OBSERVE"
    RESEARCH = "RESEARCH"
    IDEATE = "IDEATE"
    SELECT = "SELECT"
    DESIGN = "DESIGN"
    IMPLEMENT = "IMPLEMENT"
    TEST = "TEST"
    VALIDATE = "VALIDATE"
    CRITIQUE = "CRITIQUE"
    COMPARE = "COMPARE"
    EVOLVE = "EVOLVE"
    DOCUMENT = "DOCUMENT"


STATE_ORDER = list(ResearchState)


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    taker_buy_volume: float | None = None
    open_interest: float | None = None
    funding_rate: float | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("bar timestamp must be timezone-aware")


@dataclass(frozen=True)
class Hypothesis:
    id: str
    title: str
    research_mode: str
    family: str
    economic_or_behavioral_story: str
    market_mechanism: str
    data_required: list[str]
    features: list[str]
    trigger: str
    market_context: str
    regime: str
    entry_logic: str
    exit_logic: str
    invalidators: list[str]
    time_horizon: str
    expected_failure_modes: list[str]
    novelty_claim: str
    experiments_needed: list[str]

    def canonical(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    hypothesis: Hypothesis
    dataset_version: str
    assets: list[str]
    parameters: dict[str, Any]
    training_period: str
    validation_period: str
    test_period: str
    costs: dict[str, float]
    parent_ids: list[str] = field(default_factory=list)
    engine_version: str = "next-open-v1"

    def canonical(self) -> dict[str, Any]:
        return asdict(self)

    def digest(self) -> str:
        identity = self.canonical()
        # Run labels are deliberately excluded: re-labelling the same scientific
        # specification must not bypass exact-duplicate protection.
        identity.pop("experiment_id", None)
        identity["hypothesis"].pop("id", None)
        identity["hypothesis"].pop("research_mode", None)
        payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class Trade:
    timestamp: datetime
    old_position: float
    new_position: float
    price: float
    turnover: float
    commission: float
    slippage: float


@dataclass
class BacktestResult:
    initial_equity: float
    final_equity: float
    gross_return: float
    net_return: float
    max_drawdown: float
    sharpe: float
    sortino: float
    profit_factor: float | None
    turnover: float
    exposure: float
    trades: list[Trade]
    equity_curve: list[tuple[datetime, float]]
    bar_returns: list[float]
    total_commission: float
    total_slippage: float
    total_funding: float

    def summary(self) -> dict[str, Any]:
        return {
            "initial_equity": self.initial_equity,
            "final_equity": self.final_equity,
            "gross_return": self.gross_return,
            "net_return": self.net_return,
            "drawdown": self.max_drawdown,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "profit_factor": self.profit_factor,
            "turnover": self.turnover,
            "exposure": self.exposure,
            "trades": len(self.trades),
            "total_commission": self.total_commission,
            "total_slippage": self.total_slippage,
            "total_funding": self.total_funding,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Bumped whenever a change makes previously stored results incomparable with
# new ones. Version 2 removed the volatility lookahead in position sizing
# (QUANT8): every result produced under version 1 is inflated, so it stays
# readable for audit but can never become the published champion.
ENGINE_VERSION = 2
