"""Strategy-neutral contracts for saved research observations and evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from trading.options.contracts import VersionedRecord, require_utc


class EvaluationScope(str, Enum):
    """Evaluation artifacts are estimates, never live-account records."""

    SAVED_RESEARCH_OUTCOME = "saved_research_outcome"
    WALK_FORWARD_ESTIMATE = "walk_forward_estimate"


class FoldKind(str, Enum):
    EXPANDING = "expanding"
    ROLLING = "rolling"


class EvidenceStatus(str, Enum):
    SUPPORTS_STRATEGY = "supports_strategy"
    SUPPORTS_BASELINE = "supports_baseline"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class EvaluationVersions(VersionedRecord):
    """Complete provenance needed to reproduce a research result."""

    data_version: str
    model_version: str
    strategy_version: str
    objective_version: str
    config_version: str
    code_version: str

    def __post_init__(self) -> None:
        if not all(
            (
                self.data_version,
                self.model_version,
                self.strategy_version,
                self.objective_version,
                self.config_version,
                self.code_version,
            )
        ):
            raise ValueError("all evaluation version fields are required")


@dataclass(frozen=True)
class OutcomeAttribution(VersionedRecord):
    """Additive return contributions under pessimistic executable-side fills."""

    premium: Decimal
    underlying_move: Decimal
    iv_change: Decimal
    fees: Decimal
    slippage: Decimal
    capital_opportunity_cost: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.premium
            + self.underlying_move
            + self.iv_change
            + self.fees
            + self.slippage
            + self.capital_opportunity_cost
        )


@dataclass(frozen=True)
class SavedOutcomeObservation(VersionedRecord):
    """A point-in-time saved candidate outcome supplied by any strategy.

    This represents a research label generated from historical market data.  It is
    deliberately not a realized brokerage/trading record.
    """

    observation_id: str
    candidate_id: str
    strategy_id: str
    objective_id: str
    decision_at_utc: datetime
    outcome_available_at_utc: datetime
    pessimistic_return: Decimal
    midpoint_return: Decimal
    naive_baseline_return: Decimal
    regime: str
    attribution: OutcomeAttribution
    versions: EvaluationVersions
    scope: EvaluationScope = EvaluationScope.SAVED_RESEARCH_OUTCOME

    def __post_init__(self) -> None:
        require_utc(self.decision_at_utc, "decision_at_utc")
        require_utc(self.outcome_available_at_utc, "outcome_available_at_utc")
        if not all((self.observation_id, self.candidate_id, self.strategy_id, self.objective_id)):
            raise ValueError("observation, candidate, strategy, and objective ids are required")
        if not self.regime:
            raise ValueError("regime is required")
        if self.scope is not EvaluationScope.SAVED_RESEARCH_OUTCOME:
            raise ValueError("saved observations must be research outcomes")
        if self.outcome_available_at_utc < self.decision_at_utc:
            raise ValueError("outcome cannot be available before the decision")
        if self.pessimistic_return > self.midpoint_return:
            raise ValueError("pessimistic executable-side return cannot exceed midpoint return")
        if self.attribution.total != self.pessimistic_return:
            raise ValueError("attribution must reconcile exactly to pessimistic_return")


@dataclass(frozen=True)
class WalkForwardConfig(VersionedRecord):
    fold_kind: FoldKind
    min_train_observations: int
    test_observations: int
    step_observations: int
    rolling_train_observations: int | None
    confidence_level: Decimal
    min_evaluation_observations: int
    min_effective_sample_size: Decimal
    max_regime_share: Decimal

    def __post_init__(self) -> None:
        if (
            min(
                self.min_train_observations,
                self.test_observations,
                self.step_observations,
                self.min_evaluation_observations,
            )
            <= 0
        ):
            raise ValueError("walk-forward observation counts must be positive")
        if self.fold_kind is FoldKind.ROLLING:
            if (
                self.rolling_train_observations is None
                or self.rolling_train_observations < self.min_train_observations
            ):
                raise ValueError(
                    "rolling folds require a train window at least as large as min_train"
                )
        elif self.rolling_train_observations is not None:
            raise ValueError("expanding folds do not accept rolling_train_observations")
        if not Decimal("0") < self.confidence_level < Decimal("1"):
            raise ValueError("confidence_level must be in (0, 1)")
        if self.min_effective_sample_size <= 0:
            raise ValueError("min_effective_sample_size must be positive")
        if not Decimal("0") < self.max_regime_share <= Decimal("1"):
            raise ValueError("max_regime_share must be in (0, 1]")


@dataclass(frozen=True)
class WalkForwardFold(VersionedRecord):
    fold_id: str
    train_observation_ids: tuple[str, ...]
    test_observation_ids: tuple[str, ...]
    test_started_at_utc: datetime
    test_ended_at_utc: datetime

    def __post_init__(self) -> None:
        require_utc(self.test_started_at_utc, "test_started_at_utc")
        require_utc(self.test_ended_at_utc, "test_ended_at_utc")
        if not self.fold_id or not self.train_observation_ids or not self.test_observation_ids:
            raise ValueError("fold id and non-empty train/test ids are required")
        if set(self.train_observation_ids) & set(self.test_observation_ids):
            raise ValueError("train and test observations cannot overlap")


@dataclass(frozen=True)
class ConfidenceInterval(VersionedRecord):
    mean: Decimal
    lower: Decimal
    upper: Decimal
    confidence_level: Decimal


@dataclass(frozen=True)
class AggregateAttribution(VersionedRecord):
    premium: Decimal
    underlying_move: Decimal
    iv_change: Decimal
    fees: Decimal
    slippage: Decimal
    capital_opportunity_cost: Decimal


@dataclass(frozen=True)
class WalkForwardEvaluation(VersionedRecord):
    evaluation_id: str
    strategy_id: str
    objective_id: str
    scope: EvaluationScope
    versions: EvaluationVersions
    config: WalkForwardConfig
    folds: tuple[WalkForwardFold, ...]
    observation_ids: tuple[str, ...]
    pessimistic_interval: ConfidenceInterval | None
    midpoint_interval: ConfidenceInterval | None
    excess_over_baseline_interval: ConfidenceInterval | None
    effective_sample_size: Decimal
    regime_shares: dict[str, Decimal]
    maximum_regime_share: Decimal
    attribution: AggregateAttribution | None
    status: EvidenceStatus
    evidence_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.evaluation_id or not self.strategy_id or not self.objective_id:
            raise ValueError("evaluation, strategy, and objective ids are required")
        if self.scope is not EvaluationScope.WALK_FORWARD_ESTIMATE:
            raise ValueError("walk-forward evaluations must be research estimates")
        if self.status is EvidenceStatus.INSUFFICIENT_EVIDENCE and not self.evidence_reasons:
            raise ValueError("insufficient evidence requires explicit reasons")
        if self.status is not EvidenceStatus.INSUFFICIENT_EVIDENCE and self.evidence_reasons:
            raise ValueError("supported outcomes cannot carry insufficiency reasons")
