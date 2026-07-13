"""Auditable contracts for estimated and realized objective scores."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from trading.options.contracts import VersionedRecord
from trading.portfolio import CapitalRequirement
from trading.simulation import SimulationResult


class ScoreKind(str, Enum):
    ESTIMATED = "estimated"
    REALIZED = "realized"


@dataclass(frozen=True)
class PnlOutcome(VersionedRecord):
    """One mutually exclusive estimated terminal P&L outcome."""

    outcome_id: str
    pnl: Decimal
    probability: Decimal

    def __post_init__(self) -> None:
        if not self.outcome_id:
            raise ValueError("outcome_id is required")
        if self.probability <= 0 or self.probability > 1:
            raise ValueError("outcome probability must be in (0, 1]")


@dataclass(frozen=True)
class PnlDistribution(VersionedRecord):
    """A strategy-produced estimate, never a realized lifecycle result."""

    distribution_id: str
    candidate_id: str
    forecast_bundle_id: str
    outcomes: tuple[PnlOutcome, ...]

    def __post_init__(self) -> None:
        if not self.distribution_id or not self.candidate_id or not self.forecast_bundle_id:
            raise ValueError("distribution, candidate, and forecast bundle ids are required")
        if not self.outcomes:
            raise ValueError("at least one P&L outcome is required")
        if len({item.outcome_id for item in self.outcomes}) != len(self.outcomes):
            raise ValueError("outcome ids must be unique")
        if sum((item.probability for item in self.outcomes), Decimal("0")) != Decimal("1"):
            raise ValueError("outcome probabilities must sum exactly to 1")


@dataclass(frozen=True)
class ObjectiveWeights(VersionedRecord):
    """Explicit dimensionless weights; no objective has an implicit default."""

    return_weight: Decimal
    tail_weight: Decimal
    capital_weight: Decimal
    liquidity_weight: Decimal
    concentration_weight: Decimal

    def __post_init__(self) -> None:
        values = (
            self.return_weight,
            self.tail_weight,
            self.capital_weight,
            self.liquidity_weight,
            self.concentration_weight,
        )
        if any(value < 0 for value in values):
            raise ValueError("objective weights cannot be negative")
        if sum(values, Decimal("0")) == 0:
            raise ValueError("at least one objective weight must be positive")


@dataclass(frozen=True)
class EstimatedObjectiveInput(VersionedRecord):
    distribution: PnlDistribution
    capital: CapitalRequirement
    liquidity_cost: Decimal
    concentration_penalty: Decimal
    tail_confidence: Decimal

    def __post_init__(self) -> None:
        if self.liquidity_cost < 0:
            raise ValueError("liquidity_cost cannot be negative")
        if self.concentration_penalty < 0:
            raise ValueError("concentration_penalty cannot be negative")
        if self.tail_confidence <= 0 or self.tail_confidence >= 1:
            raise ValueError("tail_confidence must be in (0, 1)")


@dataclass(frozen=True)
class RealizedObjectiveInput:
    """A realized lifecycle plus the terminal value of any delivered shares."""

    simulation: SimulationResult
    capital: CapitalRequirement
    terminal_share_price: Decimal
    liquidity_cost: Decimal
    concentration_penalty: Decimal

    def __post_init__(self) -> None:
        if min(self.terminal_share_price, self.liquidity_cost, self.concentration_penalty) < 0:
            raise ValueError("realized input prices and penalties cannot be negative")


@dataclass(frozen=True)
class ObjectiveComponents(VersionedRecord):
    """Raw metrics and normalized components used by the weighted score."""

    pnl: Decimal
    return_on_collateral: Decimal
    tail_loss: Decimal
    tail_adjusted_return: Decimal
    opportunity_cost_adjusted_return: Decimal
    return_component: Decimal
    tail_component: Decimal
    capital_component: Decimal
    liquidity_component: Decimal
    concentration_component: Decimal


@dataclass(frozen=True)
class ObjectiveScore(VersionedRecord):
    score_id: str
    source_id: str
    kind: ScoreKind
    weights: ObjectiveWeights
    components: ObjectiveComponents
    weighted_components: dict[str, Decimal]
    total_score: Decimal

    def __post_init__(self) -> None:
        if not self.score_id or not self.source_id:
            raise ValueError("score_id and source_id are required")
        expected_keys = {"return", "tail", "capital", "liquidity", "concentration"}
        if set(self.weighted_components) != expected_keys:
            raise ValueError("weighted score must expose all five objective components")
        if self.total_score != sum(self.weighted_components.values(), Decimal("0")):
            raise ValueError("total_score must equal the decomposed weighted components")
