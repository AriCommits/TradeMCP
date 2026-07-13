"""Strategy-agnostic walk-forward evaluation orchestration."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256

from .folds import build_folds
from .records import (
    AggregateAttribution,
    EvidenceStatus,
    EvaluationScope,
    SavedOutcomeObservation,
    WalkForwardConfig,
    WalkForwardEvaluation,
)
from .statistics import effective_sample_size, mean_confidence_interval


def _average_attribution(items: tuple[SavedOutcomeObservation, ...]) -> AggregateAttribution | None:
    if not items:
        return None
    divisor = Decimal(len(items))
    return AggregateAttribution(
        premium=sum((item.attribution.premium for item in items), Decimal("0")) / divisor,
        underlying_move=sum((item.attribution.underlying_move for item in items), Decimal("0"))
        / divisor,
        iv_change=sum((item.attribution.iv_change for item in items), Decimal("0")) / divisor,
        fees=sum((item.attribution.fees for item in items), Decimal("0")) / divisor,
        slippage=sum((item.attribution.slippage for item in items), Decimal("0")) / divisor,
        capital_opportunity_cost=sum(
            (item.attribution.capital_opportunity_cost for item in items), Decimal("0")
        )
        / divisor,
    )


def evaluate_walk_forward(
    observations: tuple[SavedOutcomeObservation, ...], config: WalkForwardConfig
) -> WalkForwardEvaluation:
    if not observations:
        raise ValueError("at least one saved research observation is required")
    strategy_ids = {item.strategy_id for item in observations}
    objective_ids = {item.objective_id for item in observations}
    versions = {item.versions.to_json() for item in observations}
    if len(strategy_ids) != 1 or len(objective_ids) != 1 or len(versions) != 1:
        raise ValueError("one evaluation cannot mix strategy, objective, or version identities")

    folds = build_folds(observations, config)
    by_id = {item.observation_id: item for item in observations}
    test_ids = tuple(
        dict.fromkeys(item_id for fold in folds for item_id in fold.test_observation_ids)
    )
    evaluated = tuple(by_id[item_id] for item_id in test_ids)
    pessimistic = tuple(item.pessimistic_return for item in evaluated)
    midpoint = tuple(item.midpoint_return for item in evaluated)
    excess = tuple(item.pessimistic_return - item.naive_baseline_return for item in evaluated)
    ess = effective_sample_size(excess)

    regime_counts: dict[str, int] = {}
    for item in evaluated:
        regime_counts[item.regime] = regime_counts.get(item.regime, 0) + 1
    regime_shares = (
        {
            name: Decimal(count) / Decimal(len(evaluated))
            for name, count in sorted(regime_counts.items())
        }
        if evaluated
        else {}
    )
    max_regime_share = max(regime_shares.values(), default=Decimal("0"))
    excess_interval = mean_confidence_interval(excess, config.confidence_level)
    reasons: list[str] = []
    if not folds:
        reasons.append("no_valid_point_in_time_folds")
    if len(evaluated) < config.min_evaluation_observations:
        reasons.append("insufficient_evaluation_observations")
    if ess < config.min_effective_sample_size:
        reasons.append("insufficient_effective_sample_size")
    if max_regime_share > config.max_regime_share:
        reasons.append("excessive_regime_concentration")
    if excess_interval is None or not (excess_interval.lower > 0 or excess_interval.upper < 0):
        reasons.append("baseline_difference_not_statistically_resolved")

    if reasons:
        status = EvidenceStatus.INSUFFICIENT_EVIDENCE
    elif excess_interval is not None and excess_interval.lower > 0:
        status = EvidenceStatus.SUPPORTS_STRATEGY
    else:
        status = EvidenceStatus.SUPPORTS_BASELINE

    ordered = tuple(
        sorted(observations, key=lambda item: (item.decision_at_utc, item.observation_id))
    )
    identity_payload = "|".join(
        [
            *(item.to_json() for item in ordered),
            config.to_json(),
            *(fold.to_json() for fold in folds),
        ]
    )
    identity = sha256(identity_payload.encode()).hexdigest()
    first = observations[0]
    return WalkForwardEvaluation(
        evaluation_id=f"walk-forward-{identity}",
        strategy_id=first.strategy_id,
        objective_id=first.objective_id,
        scope=EvaluationScope.WALK_FORWARD_ESTIMATE,
        versions=first.versions,
        config=config,
        folds=folds,
        observation_ids=test_ids,
        pessimistic_interval=mean_confidence_interval(pessimistic, config.confidence_level),
        midpoint_interval=mean_confidence_interval(midpoint, config.confidence_level),
        excess_over_baseline_interval=excess_interval,
        effective_sample_size=ess,
        regime_shares=regime_shares,
        maximum_regime_share=max_regime_share,
        attribution=_average_attribution(evaluated),
        status=status,
        evidence_reasons=tuple(reasons),
    )
