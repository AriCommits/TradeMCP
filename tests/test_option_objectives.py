from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from trading.objectives import (
    EstimatedObjectiveInput,
    ObjectiveScore,
    ObjectiveWeights,
    PnlDistribution,
    PnlOutcome,
    RealizedObjectiveInput,
    ScoreKind,
    StressGrid,
    StressPoint,
    build_stress_grid,
    evaluate_stress_grid,
    score_estimate,
    score_realized,
)
from trading.portfolio import CapitalRequirement, CapitalTreatment
from trading.simulation import (
    Cashflow,
    CashflowKind,
    LifecycleEvent,
    LifecycleEventKind,
    SimulationResult,
)


UTC = timezone.utc
NOW = datetime(2026, 7, 13, 20, 0, tzinfo=UTC)


def _capital(*, eligible: bool = True) -> CapitalRequirement:
    return CapitalRequirement(
        treatment=CapitalTreatment.CASH_SECURED,
        cash_required=Decimal("1000"),
        covered_shares_required=Decimal("0"),
        maximum_loss=Decimal("1000"),
        estimated_buying_power_reduction=Decimal("1000"),
        buying_power_is_estimate=True,
        estimate_basis="test",
        opportunity_cost=Decimal("10"),
        eligible=eligible,
        rejection_reasons=() if eligible else ("INSUFFICIENT_BUYING_POWER",),
    )


def _weights() -> ObjectiveWeights:
    return ObjectiveWeights(
        return_weight=Decimal("1"),
        tail_weight=Decimal("0.5"),
        capital_weight=Decimal("1"),
        liquidity_weight=Decimal("1"),
        concentration_weight=Decimal("1"),
    )


def _distribution() -> PnlDistribution:
    return PnlDistribution(
        distribution_id="dist-1",
        candidate_id="candidate-1",
        forecast_bundle_id="bundle-1",
        outcomes=(
            PnlOutcome("profit", Decimal("100"), Decimal("0.8")),
            PnlOutcome("loss", Decimal("-400"), Decimal("0.2")),
        ),
    )


def _simulation() -> SimulationResult:
    cashflow = Cashflow(
        cashflow_id="cash-1",
        occurred_at_utc=NOW,
        kind=CashflowKind.CASH_SETTLEMENT,
        amount=Decimal("100"),
        currency="USD",
        per_share_amount=Decimal("1"),
        per_contract_amount=Decimal("100"),
        contracts=1,
        multiplier=Decimal("100"),
        description="settled gain",
    )
    event = LifecycleEvent(
        event_id="event-1",
        occurred_at_utc=NOW,
        kind=LifecycleEventKind.CASH_SETTLED,
        contract_id="contract-1",
        cashflows=(cashflow,),
    )
    return SimulationResult(
        simulation_id="simulation-1",
        contract_id="contract-1",
        events=(event,),
        final_share_delta=Decimal("0"),
        reconciled_cash=Decimal("100"),
        total_commissions=Decimal("0"),
        total_fees=Decimal("0"),
        total_slippage=Decimal("0"),
    )


def test_estimated_score_exposes_all_weighted_components() -> None:
    score = score_estimate(
        EstimatedObjectiveInput(
            distribution=_distribution(),
            capital=_capital(),
            liquidity_cost=Decimal("5"),
            concentration_penalty=Decimal("0.02"),
            tail_confidence=Decimal("0.95"),
        ),
        _weights(),
    )

    assert score.kind is ScoreKind.ESTIMATED
    assert score.components.pnl == Decimal("0")
    assert score.components.return_on_collateral == Decimal("0")
    assert score.components.tail_loss == Decimal("400")
    assert score.components.tail_adjusted_return == Decimal("-0.4")
    assert score.components.opportunity_cost_adjusted_return == Decimal("-0.01")
    assert score.weighted_components == {
        "return": Decimal("0"),
        "tail": Decimal("-0.20"),
        "capital": Decimal("-0.01"),
        "liquidity": Decimal("-0.005"),
        "concentration": Decimal("-0.02"),
    }
    assert score.total_score == Decimal("-0.235")
    assert ObjectiveScore.from_json(score.to_json()) == score


def test_realized_lifecycle_uses_distinct_score_path() -> None:
    score = score_realized(
        RealizedObjectiveInput(
            simulation=_simulation(),
            capital=_capital(),
            terminal_share_price=Decimal("99"),
            liquidity_cost=Decimal("0"),
            concentration_penalty=Decimal("0"),
        ),
        _weights(),
    )

    assert score.kind is ScoreKind.REALIZED
    assert score.source_id == "simulation-1"
    assert score.components.pnl == Decimal("100")
    assert score.components.return_on_collateral == Decimal("0.1")
    assert score.components.tail_loss == 0


def test_objective_inputs_fail_closed_on_invalid_economics() -> None:
    with pytest.raises(ValueError, match="sum exactly"):
        PnlDistribution(
            "dist",
            "candidate",
            "bundle",
            (PnlOutcome("only", Decimal("1"), Decimal("0.9")),),
        )
    with pytest.raises(ValueError, match="ineligible"):
        score_estimate(
            EstimatedObjectiveInput(
                _distribution(),
                _capital(eligible=False),
                Decimal("0"),
                Decimal("0"),
                Decimal("0.95"),
            ),
            _weights(),
        )
    with pytest.raises(ValueError, match="weight"):
        ObjectiveWeights(*(Decimal("0") for _ in range(5)))


def test_stress_grid_is_canonical_and_reproducible() -> None:
    grid = StressGrid(
        spot_shocks=(Decimal("0.1"), Decimal("-0.1")),
        iv_shocks=(Decimal("0.05"), Decimal("0")),
        time_fractions=(Decimal("1"), Decimal("0")),
        liquidity_multipliers=(Decimal("2"), Decimal("1")),
    )
    reordered = StressGrid(
        spot_shocks=tuple(reversed(grid.spot_shocks)),
        iv_shocks=tuple(reversed(grid.iv_shocks)),
        time_fractions=tuple(reversed(grid.time_fractions)),
        liquidity_multipliers=tuple(reversed(grid.liquidity_multipliers)),
    )

    assert build_stress_grid(grid) == build_stress_grid(reordered)

    def evaluator(point: StressPoint) -> Decimal:
        return point.spot_shock * Decimal("100") - point.liquidity_multiplier

    first = evaluate_stress_grid(
        grid=grid,
        base_input_identity="candidate-1:quote-1",
        evaluator_id="test-pricer",
        evaluator_version="1.0",
        evaluator=evaluator,
    )
    second = evaluate_stress_grid(
        grid=reordered,
        base_input_identity="candidate-1:quote-1",
        evaluator_id="test-pricer",
        evaluator_version="1.0",
        evaluator=evaluator,
    )

    assert first == second
    assert len(first.results) == 16
    assert first.metadata["scenario_count"] == "16"
    assert len({item.point.scenario_id for item in first.results}) == 16
