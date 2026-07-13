"""Objective calculations with separate estimated and realized entry points."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256

from .records import (
    EstimatedObjectiveInput,
    ObjectiveComponents,
    ObjectiveScore,
    ObjectiveWeights,
    RealizedObjectiveInput,
    ScoreKind,
)


def _collateral(value: EstimatedObjectiveInput | RealizedObjectiveInput) -> Decimal:
    capital = value.capital
    if not capital.eligible:
        raise ValueError("ineligible capital requirements cannot be scored")
    collateral = max(capital.cash_required, capital.estimated_buying_power_reduction)
    if collateral <= 0:
        raise ValueError("positive collateral or buying-power reduction is required")
    return collateral


def _expected_shortfall(value: EstimatedObjectiveInput) -> Decimal:
    """Average positive loss in the lowest-P&L probability mass."""

    remaining = Decimal("1") - value.tail_confidence
    tail_mass = remaining
    loss_total = Decimal("0")
    for outcome in sorted(
        value.distribution.outcomes, key=lambda item: (item.pnl, item.outcome_id)
    ):
        selected = min(remaining, outcome.probability)
        loss_total += max(-outcome.pnl, Decimal("0")) * selected
        remaining -= selected
        if remaining == 0:
            break
    return loss_total / tail_mass


def _assemble(
    *,
    source_id: str,
    kind: ScoreKind,
    pnl: Decimal,
    tail_loss: Decimal,
    value: EstimatedObjectiveInput | RealizedObjectiveInput,
    weights: ObjectiveWeights,
) -> ObjectiveScore:
    collateral = _collateral(value)
    roc = pnl / collateral
    tail_ratio = tail_loss / collateral
    opportunity_ratio = value.capital.opportunity_cost / collateral
    liquidity_ratio = value.liquidity_cost / collateral
    components = ObjectiveComponents(
        pnl=pnl,
        return_on_collateral=roc,
        tail_loss=tail_loss,
        tail_adjusted_return=roc - tail_ratio,
        opportunity_cost_adjusted_return=roc - opportunity_ratio,
        return_component=roc,
        tail_component=-tail_ratio,
        capital_component=-opportunity_ratio,
        liquidity_component=-liquidity_ratio,
        concentration_component=-value.concentration_penalty,
    )
    weighted = {
        "return": components.return_component * weights.return_weight,
        "tail": components.tail_component * weights.tail_weight,
        "capital": components.capital_component * weights.capital_weight,
        "liquidity": components.liquidity_component * weights.liquidity_weight,
        "concentration": components.concentration_component * weights.concentration_weight,
    }
    identity = sha256(
        f"{kind.value}|{source_id}|{weights.to_json()}|{components.to_json()}".encode()
    ).hexdigest()
    return ObjectiveScore(
        score_id=f"objective-{identity}",
        source_id=source_id,
        kind=kind,
        weights=weights,
        components=components,
        weighted_components=weighted,
        total_score=sum(weighted.values(), Decimal("0")),
    )


def score_estimate(value: EstimatedObjectiveInput, weights: ObjectiveWeights) -> ObjectiveScore:
    expected_pnl = sum(
        (item.pnl * item.probability for item in value.distribution.outcomes), Decimal("0")
    )
    return _assemble(
        source_id=value.distribution.distribution_id,
        kind=ScoreKind.ESTIMATED,
        pnl=expected_pnl,
        tail_loss=_expected_shortfall(value),
        value=value,
        weights=weights,
    )


def score_realized(value: RealizedObjectiveInput, weights: ObjectiveWeights) -> ObjectiveScore:
    realized_pnl = (
        value.simulation.reconciled_cash
        + value.simulation.final_share_delta * value.terminal_share_price
    )
    return _assemble(
        source_id=value.simulation.simulation_id,
        kind=ScoreKind.REALIZED,
        pnl=realized_pnl,
        tail_loss=max(-realized_pnl, Decimal("0")),
        value=value,
        weights=weights,
    )
