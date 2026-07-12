"""Records for conservative option capital and portfolio risk calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from trading.options.contracts import VersionedRecord


class CapitalTreatment(str, Enum):
    """How a position's loss is funded."""

    CASH_SECURED = "cash_secured"
    COVERED_SHARES = "covered_shares"
    DEFINED_RISK = "defined_risk"
    DEBIT_PAID = "debit_paid"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class CapitalRequirement(VersionedRecord):
    """Broker-independent capital result.

    ``estimated_buying_power_reduction`` is never represented as broker state. A
    broker adapter may replace it later with an authoritative value.
    """

    treatment: CapitalTreatment
    cash_required: Decimal
    covered_shares_required: Decimal
    maximum_loss: Decimal
    estimated_buying_power_reduction: Decimal
    buying_power_is_estimate: bool
    estimate_basis: str
    opportunity_cost: Decimal
    eligible: bool
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        values = (
            self.cash_required,
            self.covered_shares_required,
            self.maximum_loss,
            self.estimated_buying_power_reduction,
            self.opportunity_cost,
        )
        if any(value < 0 for value in values):
            raise ValueError("capital values cannot be negative")
        if not self.estimate_basis:
            raise ValueError("estimate_basis is required")
        if not self.buying_power_is_estimate:
            raise ValueError("broker-independent buying power must be labeled as an estimate")
        if self.eligible and self.rejection_reasons:
            raise ValueError("an eligible capital result cannot have rejection reasons")


@dataclass(frozen=True)
class ConcentrationLimits(VersionedRecord):
    """Maximum capital allocation as a fraction of account net liquidation."""

    symbol: Decimal
    sector: Decimal
    strategy: Decimal
    expiration: Decimal

    def __post_init__(self) -> None:
        for value in (self.symbol, self.sector, self.strategy, self.expiration):
            if value <= 0 or value > 1:
                raise ValueError("concentration limits must be in (0, 1]")


@dataclass(frozen=True)
class CapitalAllocation(VersionedRecord):
    symbol: str
    sector: str
    strategy_id: str
    expiration_date: date
    capital: Decimal

    def __post_init__(self) -> None:
        if not self.symbol or not self.sector or not self.strategy_id:
            raise ValueError("allocation dimensions are required")
        if self.capital < 0:
            raise ValueError("allocation capital cannot be negative")


@dataclass(frozen=True)
class ConcentrationResult(VersionedRecord):
    eligible: bool
    symbol_fraction: Decimal
    sector_fraction: Decimal
    strategy_fraction: Decimal
    expiration_fraction: Decimal
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        fractions = (
            self.symbol_fraction,
            self.sector_fraction,
            self.strategy_fraction,
            self.expiration_fraction,
        )
        if any(value < 0 for value in fractions):
            raise ValueError("concentration fractions cannot be negative")
        if self.eligible and self.rejection_reasons:
            raise ValueError("an eligible concentration result cannot have rejection reasons")


@dataclass(frozen=True)
class GreekExposure(VersionedRecord):
    """Signed aggregate Greeks after quantity and contract multiplier."""

    delta: Decimal
    gamma: Decimal
    vega: Decimal
    theta: Decimal
