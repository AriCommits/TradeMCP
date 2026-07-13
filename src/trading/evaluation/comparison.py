"""Comparable risk summaries for independently evaluated option strategies."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256

from trading.options.contracts import VersionedRecord

from .records import EvidenceStatus, WalkForwardEvaluation


@dataclass(frozen=True)
class RiskOutcomeSupplement(VersionedRecord):
    """Saved risk labels that remain separate from generic return observations."""

    observation_id: str
    candidate_id: str
    tail_loss: Decimal
    assigned: bool
    capital_required: Decimal

    def __post_init__(self) -> None:
        if not self.observation_id or not self.candidate_id:
            raise ValueError("observation_id and candidate_id are required")
        if self.tail_loss < 0:
            raise ValueError("tail_loss cannot be negative")
        if self.capital_required <= 0:
            raise ValueError("capital_required must be positive")


@dataclass(frozen=True)
class StrategyComparisonMetrics(VersionedRecord):
    strategy_id: str
    pessimistic_mean_return: Decimal
    midpoint_mean_return: Decimal
    fill_sensitivity: Decimal
    mean_tail_loss: Decimal
    assignment_rate: Decimal
    mean_capital_required: Decimal
    effective_sample_size: Decimal
    maximum_regime_share: Decimal
    evidence_status: EvidenceStatus


@dataclass(frozen=True)
class StrategyComparisonReport(VersionedRecord):
    comparison_id: str
    objective_id: str
    left: StrategyComparisonMetrics
    right: StrategyComparisonMetrics
    preferred_strategy_id: str | None
    evidence_reasons: tuple[str, ...]
    comparison_method: str

    def __post_init__(self) -> None:
        if not self.comparison_id or not self.objective_id or not self.comparison_method:
            raise ValueError("comparison identity and method are required")
        if self.left.strategy_id == self.right.strategy_id:
            raise ValueError("a comparison requires two different strategies")
        if self.preferred_strategy_id is None and not self.evidence_reasons:
            raise ValueError("an unresolved comparison requires explicit evidence reasons")
        if self.preferred_strategy_id is not None:
            supported = {self.left.strategy_id, self.right.strategy_id}
            if self.preferred_strategy_id not in supported:
                raise ValueError("preferred_strategy_id must identify a compared strategy")
            if self.evidence_reasons:
                raise ValueError("a resolved comparison cannot carry insufficiency reasons")


def _validate_shared_assumptions(
    left: WalkForwardEvaluation,
    right: WalkForwardEvaluation,
) -> None:
    if left.objective_id != right.objective_id:
        raise ValueError("strategies must use the same objective")
    if left.config.to_json() != right.config.to_json():
        raise ValueError("strategies must use identical evaluation configuration")
    shared_version_fields = (
        "data_version",
        "model_version",
        "objective_version",
        "config_version",
        "code_version",
    )
    mismatches = [
        name
        for name in shared_version_fields
        if getattr(left.versions, name) != getattr(right.versions, name)
    ]
    if mismatches:
        raise ValueError(f"strategies do not share reproducible assumptions: {mismatches!r}")


def _metrics(
    evaluation: WalkForwardEvaluation,
    risk: tuple[RiskOutcomeSupplement, ...],
) -> StrategyComparisonMetrics:
    if evaluation.pessimistic_interval is None or evaluation.midpoint_interval is None:
        raise ValueError("comparison requires non-empty return intervals")
    if len({item.observation_id for item in risk}) != len(risk):
        raise ValueError("risk supplement observation ids must be unique")
    by_id = {item.observation_id: item for item in risk}
    if set(by_id) != set(evaluation.observation_ids):
        raise ValueError("risk supplements must exactly cover evaluated observations")
    selected = tuple(by_id[item_id] for item_id in evaluation.observation_ids)
    count = Decimal(len(selected))
    midpoint_mean = evaluation.midpoint_interval.mean
    pessimistic_mean = evaluation.pessimistic_interval.mean
    return StrategyComparisonMetrics(
        strategy_id=evaluation.strategy_id,
        pessimistic_mean_return=pessimistic_mean,
        midpoint_mean_return=midpoint_mean,
        fill_sensitivity=midpoint_mean - pessimistic_mean,
        mean_tail_loss=sum((item.tail_loss for item in selected), Decimal("0")) / count,
        assignment_rate=Decimal(sum(item.assigned for item in selected)) / count,
        mean_capital_required=(
            sum((item.capital_required for item in selected), Decimal("0")) / count
        ),
        effective_sample_size=evaluation.effective_sample_size,
        maximum_regime_share=evaluation.maximum_regime_share,
        evidence_status=evaluation.status,
    )


def compare_strategy_evaluations(
    left: WalkForwardEvaluation,
    right: WalkForwardEvaluation,
    *,
    left_risk: tuple[RiskOutcomeSupplement, ...],
    right_risk: tuple[RiskOutcomeSupplement, ...],
) -> StrategyComparisonReport:
    """Compare independent walk-forward estimates without forcing a winner."""

    _validate_shared_assumptions(left, right)
    left_metrics = _metrics(left, left_risk)
    right_metrics = _metrics(right, right_risk)
    reasons: list[str] = []
    preferred: str | None = None
    if left.status is EvidenceStatus.INSUFFICIENT_EVIDENCE:
        reasons.append(f"{left.strategy_id}:insufficient_evidence")
    if right.status is EvidenceStatus.INSUFFICIENT_EVIDENCE:
        reasons.append(f"{right.strategy_id}:insufficient_evidence")
    if not reasons:
        assert left.pessimistic_interval is not None
        assert right.pessimistic_interval is not None
        if left.pessimistic_interval.lower > right.pessimistic_interval.upper:
            preferred = left.strategy_id
        elif right.pessimistic_interval.lower > left.pessimistic_interval.upper:
            preferred = right.strategy_id
        else:
            reasons.append("pessimistic_return_intervals_overlap")

    payload = "|".join(
        (
            left.evaluation_id,
            right.evaluation_id,
            *(item.to_json() for item in sorted(left_risk, key=lambda item: item.observation_id)),
            *(item.to_json() for item in sorted(right_risk, key=lambda item: item.observation_id)),
        )
    )
    identity = sha256(payload.encode()).hexdigest()
    return StrategyComparisonReport(
        comparison_id=f"strategy-comparison-{identity}",
        objective_id=left.objective_id,
        left=left_metrics,
        right=right_metrics,
        preferred_strategy_id=preferred,
        evidence_reasons=tuple(reasons),
        comparison_method="non_overlapping_pessimistic_return_confidence_intervals",
    )
