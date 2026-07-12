"""Explicit option commission and fee schedules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TransactionCostModel:
    commission_per_contract: Decimal = Decimal("0")
    fee_per_contract: Decimal = Decimal("0")
    minimum_commission: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if any(
            value < 0
            for value in (
                self.commission_per_contract,
                self.fee_per_contract,
                self.minimum_commission,
            )
        ):
            raise ValueError("transaction costs cannot be negative")

    def calculate(self, contracts: int) -> tuple[Decimal, Decimal]:
        if contracts <= 0:
            raise ValueError("contracts must be positive")
        commission = max(self.minimum_commission, self.commission_per_contract * contracts)
        return commission, self.fee_per_contract * contracts
