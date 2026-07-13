from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import yaml

from trading.evaluation import (
    EvaluationVersions,
    FoldKind,
    OutcomeAttribution,
    SavedOutcomeObservation,
    WalkForwardConfig,
    evaluate_walk_forward,
)
from trading.evaluation.comparison import (
    RiskOutcomeSupplement,
    compare_strategy_evaluations,
)
from trading.strategies import StrategyRegistry
from trading.strategies.cash_secured_put import build_cash_secured_put_strategy
from trading.strategies.weekend_short_put import build_weekend_short_put_strategy


UTC = timezone.utc
START = datetime(2026, 1, 2, 21, 0, tzinfo=UTC)


def _versions() -> EvaluationVersions:
    return EvaluationVersions(
        data_version="saved-chain-v1",
        model_version="forecast-v1",
        strategy_version="1.0.0",
        objective_version="tail-roc-v1",
        config_version="comparison-v1",
        code_version="fixture-code",
    )


def _observations(strategy_id: str, value: Decimal) -> tuple[SavedOutcomeObservation, ...]:
    return tuple(
        SavedOutcomeObservation(
            observation_id=f"{strategy_id}-{index}",
            candidate_id=f"candidate-{strategy_id}-{index}",
            strategy_id=strategy_id,
            objective_id="tail_adjusted_return_on_collateral",
            decision_at_utc=START + timedelta(days=index),
            outcome_available_at_utc=START + timedelta(days=index, hours=1),
            pessimistic_return=value,
            midpoint_return=value + Decimal("0.002"),
            naive_baseline_return=Decimal("0"),
            regime="normal" if index % 2 else "volatile",
            attribution=OutcomeAttribution(
                premium=value + Decimal("0.004"),
                underlying_move=Decimal("0"),
                iv_change=Decimal("0"),
                fees=Decimal("-0.001"),
                slippage=Decimal("-0.002"),
                capital_opportunity_cost=Decimal("-0.001"),
            ),
            versions=_versions(),
        )
        for index in range(12)
    )


def _config() -> WalkForwardConfig:
    return WalkForwardConfig(
        fold_kind=FoldKind.EXPANDING,
        min_train_observations=3,
        test_observations=2,
        step_observations=2,
        rolling_train_observations=None,
        confidence_level=Decimal("0.95"),
        min_evaluation_observations=4,
        min_effective_sample_size=Decimal("3"),
        max_regime_share=Decimal("0.75"),
    )


def _risk(
    evaluation_ids: tuple[str, ...],
    strategy_id: str,
    *,
    tail_loss: Decimal,
    capital: Decimal,
) -> tuple[RiskOutcomeSupplement, ...]:
    return tuple(
        RiskOutcomeSupplement(
            observation_id=observation_id,
            candidate_id=f"risk-{observation_id}",
            tail_loss=tail_loss,
            assigned=index % 4 == 0,
            capital_required=capital,
        )
        for index, observation_id in enumerate(evaluation_ids)
    )


def test_reference_strategies_share_one_evaluator_and_comparison_contract() -> None:
    registry = StrategyRegistry()
    registry.discover((build_weekend_short_put_strategy(), build_cash_secured_put_strategy()))
    assert registry.keys() == (
        ("cash_secured_put_30_45_dte", "1.0.0"),
        ("weekend_short_put", "1.0.0"),
    )

    weekend = evaluate_walk_forward(
        _observations("weekend_short_put", Decimal("0.04")),
        _config(),
    )
    longer = evaluate_walk_forward(
        _observations("cash_secured_put_30_45_dte", Decimal("0.01")),
        _config(),
    )
    report = compare_strategy_evaluations(
        weekend,
        longer,
        left_risk=_risk(
            weekend.observation_ids,
            weekend.strategy_id,
            tail_loss=Decimal("0.08"),
            capital=Decimal("59000"),
        ),
        right_risk=_risk(
            longer.observation_ids,
            longer.strategy_id,
            tail_loss=Decimal("0.05"),
            capital=Decimal("5000"),
        ),
    )

    assert report.preferred_strategy_id == "weekend_short_put"
    assert report.left.fill_sensitivity == Decimal("0.002")
    assert report.left.mean_tail_loss == Decimal("0.08")
    assert report.left.assignment_rate == Decimal(1) / Decimal(3)
    assert report.right.mean_capital_required == Decimal("5000")


def test_comparison_returns_insufficient_evidence_when_intervals_overlap() -> None:
    left = evaluate_walk_forward(
        _observations("weekend_short_put", Decimal("0.02")),
        _config(),
    )
    right = evaluate_walk_forward(
        _observations("cash_secured_put_30_45_dte", Decimal("0.02")),
        _config(),
    )
    report = compare_strategy_evaluations(
        left,
        right,
        left_risk=_risk(
            left.observation_ids,
            left.strategy_id,
            tail_loss=Decimal("0.05"),
            capital=Decimal("59000"),
        ),
        right_risk=_risk(
            right.observation_ids,
            right.strategy_id,
            tail_loss=Decimal("0.05"),
            capital=Decimal("5000"),
        ),
    )

    assert report.preferred_strategy_id is None
    assert report.evidence_reasons == ("pessimistic_return_intervals_overlap",)


def test_reference_comparison_config_preserves_identical_assumptions() -> None:
    path = (
        Path(__file__).parents[1]
        / "config"
        / "options"
        / "comparisons"
        / "weekend_vs_30_45_dte.yaml"
    )
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert [item["strategy_id"] for item in payload["strategies"]] == [
        "weekend_short_put",
        "cash_secured_put_30_45_dte",
    ]
    assert payload["shared_assumptions"]["primary_fill"] == "pessimistic_executable_side"
    assert payload["evidence"]["allow_insufficient_evidence"] is True
