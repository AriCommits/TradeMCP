"""Immutable, auditable records emitted by the option lifecycle engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from trading.options.contracts import VersionedRecord, require_utc


class CashflowKind(str, Enum):
    PREMIUM = "premium"
    CLOSE = "close"
    COMMISSION = "commission"
    FEE = "fee"
    ASSIGNMENT = "assignment"
    CASH_SETTLEMENT = "cash_settlement"


class LifecycleEventKind(str, Enum):
    OPENED = "opened"
    CLOSED = "closed"
    EXPIRED_WORTHLESS = "expired_worthless"
    ASSIGNED = "assigned"
    CASH_SETTLED = "cash_settled"


@dataclass(frozen=True)
class Cashflow(VersionedRecord):
    """A signed cash movement with both share and contract units explicit."""

    cashflow_id: str
    occurred_at_utc: datetime
    kind: CashflowKind
    amount: Decimal
    currency: str
    per_share_amount: Decimal
    per_contract_amount: Decimal
    contracts: int
    multiplier: Decimal
    description: str

    def __post_init__(self) -> None:
        require_utc(self.occurred_at_utc, "occurred_at_utc")
        if not self.cashflow_id or not self.description:
            raise ValueError("cashflow_id and description are required")
        if self.contracts <= 0 or self.multiplier <= 0:
            raise ValueError("contracts and multiplier must be positive")
        if len(self.currency) != 3 or self.currency.upper() != self.currency:
            raise ValueError("currency must be an uppercase ISO-style code")
        if self.amount != self.per_contract_amount * self.contracts:
            raise ValueError("amount must equal per_contract_amount times contracts")
        if self.per_contract_amount != self.per_share_amount * self.multiplier:
            raise ValueError("per-contract amount must equal per-share amount times multiplier")


@dataclass(frozen=True)
class LifecycleEvent(VersionedRecord):
    event_id: str
    occurred_at_utc: datetime
    kind: LifecycleEventKind
    contract_id: str
    cashflows: tuple[Cashflow, ...]
    share_delta: Decimal = Decimal("0")
    details: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_utc(self.occurred_at_utc, "occurred_at_utc")
        if not self.event_id or not self.contract_id:
            raise ValueError("event_id and contract_id are required")
        if any(flow.occurred_at_utc != self.occurred_at_utc for flow in self.cashflows):
            raise ValueError("event cashflows must share the event timestamp")

    @property
    def net_cashflow(self) -> Decimal:
        return sum((flow.amount for flow in self.cashflows), Decimal("0"))


@dataclass(frozen=True)
class SimulationResult(VersionedRecord):
    simulation_id: str
    contract_id: str
    events: tuple[LifecycleEvent, ...]
    final_share_delta: Decimal
    reconciled_cash: Decimal
    total_commissions: Decimal
    total_fees: Decimal
    total_slippage: Decimal

    def __post_init__(self) -> None:
        if not self.simulation_id or not self.contract_id or not self.events:
            raise ValueError("simulation_id, contract_id, and events are required")
        if any(event.contract_id != self.contract_id for event in self.events):
            raise ValueError("all events must reference the result contract")
        if any(
            later.occurred_at_utc < earlier.occurred_at_utc
            for earlier, later in zip(self.events, self.events[1:])
        ):
            raise ValueError("lifecycle events must be chronological")
        if len({event.event_id for event in self.events}) != len(self.events):
            raise ValueError("lifecycle event ids must be unique")
        calculated_cash = sum((event.net_cashflow for event in self.events), Decimal("0"))
        calculated_shares = sum((event.share_delta for event in self.events), Decimal("0"))
        if self.reconciled_cash != calculated_cash:
            raise ValueError("reconciled_cash does not equal lifecycle cashflows")
        if self.final_share_delta != calculated_shares:
            raise ValueError("final_share_delta does not equal lifecycle share movements")
        if any(
            value < 0 for value in (self.total_commissions, self.total_fees, self.total_slippage)
        ):
            raise ValueError("cost totals cannot be negative")
