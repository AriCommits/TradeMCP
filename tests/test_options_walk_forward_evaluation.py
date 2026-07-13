from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trading.evaluation import (
    EvidenceStatus,
    EvaluationScope,
    EvaluationVersions,
    FoldKind,
    OutcomeAttribution,
    SavedOutcomeObservation,
    WalkForwardConfig,
    build_folds,
    evaluate_walk_forward,
)


UTC = timezone.utc
START = datetime(2026, 1, 2, 21, tzinfo=UTC)
VERSIONS = EvaluationVersions(
    data_version="quotes-2026-01",
    model_version="forecast-1",
    strategy_version="1.0.0",
    objective_version="roc-1",
    config_version="eval-1",
    code_version="abc123",
)


def observation(
    index: int,
    *,
    result: str = "0.02",
    baseline: str = "0",
    available_days: int = 1,
    regime: str = "normal",
    strategy: str = "weekend_short_put",
) -> SavedOutcomeObservation:
    pessimistic = Decimal(result)
    attribution = OutcomeAttribution(
        premium=Decimal("0.035"),
        underlying_move=pessimistic - Decimal("0.025"),
        iv_change=Decimal("0.005"),
        fees=Decimal("-0.002"),
        slippage=Decimal("-0.003"),
        capital_opportunity_cost=Decimal("-0.010"),
    )
    return SavedOutcomeObservation(
        observation_id=f"obs-{index}",
        candidate_id=f"candidate-{index}",
        strategy_id=strategy,
        objective_id="tail-adjusted-roc",
        decision_at_utc=START + timedelta(days=index),
        outcome_available_at_utc=START + timedelta(days=index + available_days),
        pessimistic_return=pessimistic,
        midpoint_return=pessimistic + Decimal("0.003"),
        naive_baseline_return=Decimal(baseline),
        regime=regime,
        attribution=attribution,
        versions=VERSIONS,
    )


def config(**overrides: object) -> WalkForwardConfig:
    values: dict[str, object] = {
        "fold_kind": FoldKind.EXPANDING,
        "min_train_observations": 3,
        "test_observations": 2,
        "step_observations": 2,
        "rolling_train_observations": None,
        "confidence_level": Decimal("0.95"),
        "min_evaluation_observations": 4,
        "min_effective_sample_size": Decimal("3"),
        "max_regime_share": Decimal("1"),
    }
    values.update(overrides)
    return WalkForwardConfig(**values)  # type: ignore[arg-type]


def test_saved_outcome_reconciles_and_is_research_only() -> None:
    item = observation(0)
    assert item.scope is EvaluationScope.SAVED_RESEARCH_OUTCOME
    with pytest.raises(ValueError, match="reconcile"):
        SavedOutcomeObservation(**{**item.__dict__, "pessimistic_return": Decimal("0.019")})


def test_folds_only_train_on_labels_available_before_test() -> None:
    items = tuple(observation(index, available_days=2) for index in range(9))
    folds = build_folds(items, config(min_train_observations=2))
    assert folds
    by_id = {item.observation_id: item for item in items}
    for fold in folds:
        for train_id in fold.train_observation_ids:
            assert by_id[train_id].outcome_available_at_utc < fold.test_started_at_utc
        assert set(fold.train_observation_ids).isdisjoint(fold.test_observation_ids)


def test_rolling_fold_caps_training_window() -> None:
    items = tuple(observation(index) for index in range(12))
    folds = build_folds(
        items,
        config(
            fold_kind=FoldKind.ROLLING,
            rolling_train_observations=4,
            min_train_observations=3,
        ),
    )
    assert folds
    assert all(len(fold.train_observation_ids) <= 4 for fold in folds)


def test_evaluation_reports_pessimistic_midpoint_baseline_and_attribution() -> None:
    items = tuple(
        observation(index, regime="calm" if index % 2 else "volatile") for index in range(11)
    )
    result = evaluate_walk_forward(items, config())
    assert result.scope is EvaluationScope.WALK_FORWARD_ESTIMATE
    assert result.pessimistic_interval is not None
    assert result.midpoint_interval is not None
    assert result.excess_over_baseline_interval is not None
    assert result.midpoint_interval.mean > result.pessimistic_interval.mean
    assert result.attribution is not None
    assert result.attribution.slippage == Decimal("-0.003")
    assert result.regime_shares.keys() == {"calm", "volatile"}
    assert result.status is EvidenceStatus.SUPPORTS_STRATEGY


def test_insufficient_evidence_is_explicit_not_a_forced_winner() -> None:
    items = tuple(
        observation(index, result="0.01" if index % 2 else "-0.01", regime="single")
        for index in range(8)
    )
    result = evaluate_walk_forward(
        items,
        config(min_evaluation_observations=20, max_regime_share=Decimal("0.75")),
    )
    assert result.status is EvidenceStatus.INSUFFICIENT_EVIDENCE
    assert "insufficient_evaluation_observations" in result.evidence_reasons
    assert "excessive_regime_concentration" in result.evidence_reasons
    assert "baseline_difference_not_statistically_resolved" in result.evidence_reasons


def test_identity_is_deterministic_and_input_order_independent() -> None:
    items = tuple(observation(index) for index in range(9))
    forward = evaluate_walk_forward(items, config())
    reverse = evaluate_walk_forward(tuple(reversed(items)), config())
    assert forward.evaluation_id == reverse.evaluation_id
    assert forward.to_json() == reverse.to_json()


def test_mixed_strategy_or_version_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="cannot mix"):
        evaluate_walk_forward(
            (observation(0), observation(1, strategy="cash_secured_put_30_45_dte")),
            config(min_train_observations=1),
        )
