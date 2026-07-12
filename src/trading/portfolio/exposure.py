"""Concentration gates and canonical option Greek aggregation."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from trading.options.contracts import LegSide, OptionLeg
from trading.options.greeks import OptionGreeks
from trading.strategies.specifications import AccountSnapshot

from .records import (
    CapitalAllocation,
    ConcentrationLimits,
    ConcentrationResult,
    GreekExposure,
)


def check_concentration(
    candidate: CapitalAllocation,
    existing: Iterable[CapitalAllocation],
    *,
    account: AccountSnapshot,
    limits: ConcentrationLimits,
) -> ConcentrationResult:
    """Gate capital concentration including the proposed allocation."""

    if account.net_liquidation <= 0:
        raise ValueError("positive account net liquidation is required")
    allocations = (*tuple(existing), candidate)

    def fraction(attribute: str, value: object) -> Decimal:
        capital = sum(
            (item.capital for item in allocations if getattr(item, attribute) == value),
            start=Decimal("0"),
        )
        return capital / account.net_liquidation

    symbol = fraction("symbol", candidate.symbol)
    sector = fraction("sector", candidate.sector)
    strategy = fraction("strategy_id", candidate.strategy_id)
    expiration = fraction("expiration_date", candidate.expiration_date)
    reasons: list[str] = []
    for name, value, limit in (
        ("symbol", symbol, limits.symbol),
        ("sector", sector, limits.sector),
        ("strategy", strategy, limits.strategy),
        ("expiration", expiration, limits.expiration),
    ):
        if value > limit:
            reasons.append(f"{name} concentration limit exceeded")
    return ConcentrationResult(
        eligible=not reasons,
        symbol_fraction=symbol,
        sector_fraction=sector,
        strategy_fraction=strategy,
        expiration_fraction=expiration,
        rejection_reasons=tuple(reasons),
    )


def aggregate_option_greeks(
    positions: Iterable[tuple[OptionLeg, OptionGreeks]],
) -> GreekExposure:
    """Aggregate signed Greeks using per-share canonical Greek units."""

    totals = [Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")]
    for leg, greeks in positions:
        sign = Decimal("1") if leg.side is LegSide.LONG else Decimal("-1")
        scale = sign * leg.contract.multiplier * leg.quantity
        for index, value in enumerate((greeks.delta, greeks.gamma, greeks.vega, greeks.theta)):
            totals[index] += Decimal(str(value)) * scale
    return GreekExposure(*totals)
