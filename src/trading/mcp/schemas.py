"""MCP-facing schemas for explainable, reviewable option trade plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from trading.options.contracts import VersionedRecord, require_utc
from trading.strategies.specifications import CandidatePosition, SimulationSummary


class TradePlanStatus(str, Enum):
    DRAFT = "draft"
    GO = "go"
    NO_GO = "no_go"
    NEEDS_INPUT = "needs_input"


@dataclass(frozen=True)
class ObjectiveScore(VersionedRecord):
    objective_id: str
    score: float
    components: dict[str, float]
    assumptions: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.objective_id:
            raise ValueError("objective_id is required")


@dataclass(frozen=True)
class RiskSummary(VersionedRecord):
    max_profit: Decimal | None
    max_loss: Decimal | None
    breakevens: tuple[Decimal, ...]
    expected_shortfall: Decimal | None
    probability_of_profit: float | None
    probability_of_touch: float | None
    probability_of_assignment: float | None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        probabilities = (
            self.probability_of_profit,
            self.probability_of_touch,
            self.probability_of_assignment,
        )
        if any(value is not None and not 0.0 <= value <= 1.0 for value in probabilities):
            raise ValueError("risk probabilities must be in [0, 1]")


@dataclass(frozen=True)
class StressResult(VersionedRecord):
    scenario_id: str
    spot_shock: float
    iv_shock: float
    elapsed_calendar_days: int
    estimated_pnl: Decimal

    def __post_init__(self) -> None:
        if not self.scenario_id or self.elapsed_calendar_days < 0:
            raise ValueError("scenario_id is required and elapsed days cannot be negative")


@dataclass(frozen=True)
class DataFreshness(VersionedRecord):
    market_as_of_utc: datetime
    account_as_of_utc: datetime
    generated_at_utc: datetime
    stale_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_utc(self.market_as_of_utc, "market_as_of_utc")
        require_utc(self.account_as_of_utc, "account_as_of_utc")
        require_utc(self.generated_at_utc, "generated_at_utc")
        if self.market_as_of_utc > self.generated_at_utc:
            raise ValueError("market data cannot be newer than plan generation")
        if self.account_as_of_utc > self.generated_at_utc:
            raise ValueError("account data cannot be newer than plan generation")


@dataclass(frozen=True)
class TradePlan(VersionedRecord):
    trade_plan_id: str
    created_at_utc: datetime
    run_id: str
    candidate: CandidatePosition
    objective: ObjectiveScore
    simulations: tuple[SimulationSummary, ...]
    risk: RiskSummary
    stress_results: tuple[StressResult, ...]
    data_freshness: DataFreshness
    status: TradePlanStatus
    rank: int | None
    rationale: tuple[str, ...]
    assumptions: tuple[str, ...]
    rejected_alternative_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_utc(self.created_at_utc, "created_at_utc")
        if not self.trade_plan_id or not self.run_id:
            raise ValueError("trade_plan_id and run_id are required")
        if self.rank is not None and self.rank <= 0:
            raise ValueError("rank must be positive when supplied")
        if any(item.candidate_id != self.candidate.candidate_id for item in self.simulations):
            raise ValueError("all simulations must refer to the selected candidate")
