"""Auditable single-leg short-option lifecycle simulation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from trading.options.contracts import (
    OptionContract,
    OptionType,
    SettlementType,
    require_utc,
)
from trading.options.quotes import OptionQuote

from .costs import TransactionCostModel
from .fills import Fill, FillPolicy, OrderAction
from .records import (
    Cashflow,
    CashflowKind,
    LifecycleEvent,
    LifecycleEventKind,
    SimulationResult,
)


class AssignmentHook(Protocol):
    """Optional policy for path-dependent early assignment decisions."""

    def should_assign(
        self, contract: OptionContract, at_utc: datetime, underlying_price: Decimal
    ) -> bool: ...


class ExpirationAssignmentHook(Protocol):
    """Policy for expiration exercise/assignment conventions."""

    def should_assign(self, contract: OptionContract, settlement_price: Decimal) -> bool: ...


@dataclass(frozen=True)
class IntrinsicExpirationAssignment:
    def should_assign(self, contract: OptionContract, settlement_price: Decimal) -> bool:
        if contract.option_type is OptionType.PUT:
            return settlement_price < contract.strike
        return settlement_price > contract.strike


@dataclass(frozen=True)
class NeverEarlyAssign:
    def should_assign(
        self, contract: OptionContract, at_utc: datetime, underlying_price: Decimal
    ) -> bool:
        return False


def _validate_quote(contract: OptionContract, quote: OptionQuote, at_utc: datetime) -> None:
    require_utc(at_utc, "at_utc")
    if quote.contract_id != contract.contract_id:
        raise ValueError("quote contract_id does not match the simulated contract")
    if at_utc >= contract.expiration_at_utc:
        raise ValueError("option transaction cannot occur at or after expiration")


def _trade_event(
    *,
    simulation_id: str,
    event_number: int,
    kind: LifecycleEventKind,
    contract: OptionContract,
    contracts: int,
    at_utc: datetime,
    fill: Fill,
    action: OrderAction,
    cost_model: TransactionCostModel,
) -> tuple[LifecycleEvent, Decimal, Decimal, Decimal]:
    commission, fee = cost_model.calculate(contracts)
    units = contract.multiplier * contracts
    gross = fill.price * units
    signed_gross = gross if action is OrderAction.SELL else -gross
    prefix = f"{simulation_id}:{event_number}"
    gross_kind = CashflowKind.PREMIUM if kind is LifecycleEventKind.OPENED else CashflowKind.CLOSE
    cashflows = [
        Cashflow(
            cashflow_id=f"{prefix}:gross",
            occurred_at_utc=at_utc,
            kind=gross_kind,
            amount=signed_gross,
            currency=contract.currency,
            per_share_amount=fill.price if action is OrderAction.SELL else -fill.price,
            per_contract_amount=(
                fill.price * contract.multiplier
                if action is OrderAction.SELL
                else -(fill.price * contract.multiplier)
            ),
            contracts=contracts,
            multiplier=contract.multiplier,
            description=f"{action.value} option at {fill.policy} fill",
        )
    ]
    if commission:
        cashflows.append(
            Cashflow(
                cashflow_id=f"{prefix}:commission",
                occurred_at_utc=at_utc,
                kind=CashflowKind.COMMISSION,
                amount=-commission,
                currency=contract.currency,
                per_share_amount=-(commission / units),
                per_contract_amount=-(commission / contracts),
                contracts=contracts,
                multiplier=contract.multiplier,
                description="option commission",
            )
        )
    if fee:
        cashflows.append(
            Cashflow(
                cashflow_id=f"{prefix}:fee",
                occurred_at_utc=at_utc,
                kind=CashflowKind.FEE,
                amount=-fee,
                currency=contract.currency,
                per_share_amount=-(fee / units),
                per_contract_amount=-(fee / contracts),
                contracts=contracts,
                multiplier=contract.multiplier,
                description="option regulatory and exchange fees",
            )
        )
    event = LifecycleEvent(
        event_id=prefix,
        occurred_at_utc=at_utc,
        kind=kind,
        contract_id=contract.contract_id,
        cashflows=tuple(cashflows),
        details=(
            f"fill_policy={fill.policy}",
            f"fill_price_per_share={fill.price}",
            f"reference_midpoint={fill.reference_midpoint}",
        ),
    )
    slippage = fill.adverse_slippage_per_share * units
    return event, commission, fee, slippage


def _result(
    simulation_id: str,
    contract: OptionContract,
    events: tuple[LifecycleEvent, ...],
    commissions: Decimal,
    fees: Decimal,
    slippage: Decimal,
) -> SimulationResult:
    return SimulationResult(
        simulation_id=simulation_id,
        contract_id=contract.contract_id,
        events=events,
        final_share_delta=sum((event.share_delta for event in events), Decimal("0")),
        reconciled_cash=sum((event.net_cashflow for event in events), Decimal("0")),
        total_commissions=commissions,
        total_fees=fees,
        total_slippage=slippage,
    )


@dataclass(frozen=True)
class ShortPutSimulator:
    fill_policy: FillPolicy
    cost_model: TransactionCostModel = TransactionCostModel()
    early_assignment_hook: AssignmentHook = NeverEarlyAssign()
    expiration_assignment_hook: ExpirationAssignmentHook = IntrinsicExpirationAssignment()

    def _validate(self, contract: OptionContract, contracts: int) -> None:
        if contract.option_type is not OptionType.PUT:
            raise ValueError("ShortPutSimulator requires a put contract")
        if contract.settlement_type is not SettlementType.PHYSICAL:
            raise ValueError("cash-settled short puts are not supported")
        if contracts <= 0:
            raise ValueError("contracts must be positive")

    def simulate_close(
        self,
        *,
        simulation_id: str,
        contract: OptionContract,
        contracts: int,
        open_quote: OptionQuote,
        opened_at_utc: datetime,
        close_quote: OptionQuote,
        closed_at_utc: datetime,
    ) -> SimulationResult:
        self._validate(contract, contracts)
        _validate_quote(contract, open_quote, opened_at_utc)
        _validate_quote(contract, close_quote, closed_at_utc)
        if closed_at_utc <= opened_at_utc:
            raise ValueError("close timestamp must be after open timestamp")
        open_fill = self.fill_policy.fill(open_quote, OrderAction.SELL, opened_at_utc)
        close_fill = self.fill_policy.fill(close_quote, OrderAction.BUY, closed_at_utc)
        opened, oc, of, os = _trade_event(
            simulation_id=simulation_id,
            event_number=1,
            kind=LifecycleEventKind.OPENED,
            contract=contract,
            contracts=contracts,
            at_utc=opened_at_utc,
            fill=open_fill,
            action=OrderAction.SELL,
            cost_model=self.cost_model,
        )
        closed, cc, cf, cs = _trade_event(
            simulation_id=simulation_id,
            event_number=2,
            kind=LifecycleEventKind.CLOSED,
            contract=contract,
            contracts=contracts,
            at_utc=closed_at_utc,
            fill=close_fill,
            action=OrderAction.BUY,
            cost_model=self.cost_model,
        )
        return _result(simulation_id, contract, (opened, closed), oc + cc, of + cf, os + cs)

    def simulate_expiration(
        self,
        *,
        simulation_id: str,
        contract: OptionContract,
        contracts: int,
        open_quote: OptionQuote,
        opened_at_utc: datetime,
        settlement_underlying_price: Decimal,
    ) -> SimulationResult:
        self._validate(contract, contracts)
        _validate_quote(contract, open_quote, opened_at_utc)
        if settlement_underlying_price <= 0:
            raise ValueError("settlement_underlying_price must be positive")
        fill = self.fill_policy.fill(open_quote, OrderAction.SELL, opened_at_utc)
        opened, commission, fee, slippage = _trade_event(
            simulation_id=simulation_id,
            event_number=1,
            kind=LifecycleEventKind.OPENED,
            contract=contract,
            contracts=contracts,
            at_utc=opened_at_utc,
            fill=fill,
            action=OrderAction.SELL,
            cost_model=self.cost_model,
        )
        assigned = self.expiration_assignment_hook.should_assign(
            contract, settlement_underlying_price
        )
        if assigned:
            units = contract.multiplier * contracts
            assignment = LifecycleEvent(
                event_id=f"{simulation_id}:2",
                occurred_at_utc=contract.expiration_at_utc,
                kind=LifecycleEventKind.ASSIGNED,
                contract_id=contract.contract_id,
                cashflows=(
                    Cashflow(
                        cashflow_id=f"{simulation_id}:2:assignment",
                        occurred_at_utc=contract.expiration_at_utc,
                        kind=CashflowKind.ASSIGNMENT,
                        amount=-(contract.strike * units),
                        currency=contract.currency,
                        per_share_amount=-contract.strike,
                        per_contract_amount=-(contract.strike * contract.multiplier),
                        contracts=contracts,
                        multiplier=contract.multiplier,
                        description="physical put assignment purchase",
                    ),
                ),
                share_delta=units,
                details=(f"settlement_underlying_price={settlement_underlying_price}",),
            )
        else:
            assignment = LifecycleEvent(
                event_id=f"{simulation_id}:2",
                occurred_at_utc=contract.expiration_at_utc,
                kind=LifecycleEventKind.EXPIRED_WORTHLESS,
                contract_id=contract.contract_id,
                cashflows=(),
                details=(f"settlement_underlying_price={settlement_underlying_price}",),
            )
        return _result(
            simulation_id,
            contract,
            (opened, assignment),
            commission,
            fee,
            slippage,
        )

    def simulate_early_assignment(
        self,
        *,
        simulation_id: str,
        contract: OptionContract,
        contracts: int,
        open_quote: OptionQuote,
        opened_at_utc: datetime,
        assignment_at_utc: datetime,
        underlying_price: Decimal,
    ) -> SimulationResult:
        require_utc(assignment_at_utc, "assignment_at_utc")
        if assignment_at_utc <= opened_at_utc:
            raise ValueError("early assignment must follow the open timestamp")
        if underlying_price <= 0:
            raise ValueError("underlying_price must be positive")
        if assignment_at_utc >= contract.expiration_at_utc:
            raise ValueError("early assignment must precede expiration")
        if not self.early_assignment_hook.should_assign(
            contract, assignment_at_utc, underlying_price
        ):
            raise ValueError("early-assignment hook did not authorize assignment")
        # Reuse expiration accounting with a temporary event timestamp replacement.
        result = self.simulate_expiration(
            simulation_id=simulation_id,
            contract=contract,
            contracts=contracts,
            open_quote=open_quote,
            opened_at_utc=opened_at_utc,
            settlement_underlying_price=min(underlying_price, contract.strike - Decimal("0.01")),
        )
        event = result.events[1]
        cashflow = event.cashflows[0]
        early_cashflow = Cashflow(
            cashflow_id=cashflow.cashflow_id,
            occurred_at_utc=assignment_at_utc,
            kind=cashflow.kind,
            amount=cashflow.amount,
            currency=cashflow.currency,
            per_share_amount=cashflow.per_share_amount,
            per_contract_amount=cashflow.per_contract_amount,
            contracts=cashflow.contracts,
            multiplier=cashflow.multiplier,
            description="early physical put assignment purchase",
        )
        early_event = LifecycleEvent(
            event_id=event.event_id,
            occurred_at_utc=assignment_at_utc,
            kind=event.kind,
            contract_id=event.contract_id,
            cashflows=(early_cashflow,),
            share_delta=event.share_delta,
            details=(f"underlying_price={underlying_price}", "early_assignment=true"),
        )
        return _result(
            simulation_id,
            contract,
            (result.events[0], early_event),
            result.total_commissions,
            result.total_fees,
            result.total_slippage,
        )


@dataclass(frozen=True)
class CoveredCallSimulator:
    """Physical covered-call expiration accounting after share coverage is verified."""

    fill_policy: FillPolicy
    cost_model: TransactionCostModel = TransactionCostModel()
    expiration_assignment_hook: ExpirationAssignmentHook = IntrinsicExpirationAssignment()

    def simulate_expiration(
        self,
        *,
        simulation_id: str,
        contract: OptionContract,
        contracts: int,
        covered_shares: Decimal,
        open_quote: OptionQuote,
        opened_at_utc: datetime,
        settlement_underlying_price: Decimal,
    ) -> SimulationResult:
        if contract.option_type is not OptionType.CALL:
            raise ValueError("CoveredCallSimulator requires a call contract")
        if contract.settlement_type is not SettlementType.PHYSICAL:
            raise ValueError("cash-settled covered calls are not supported")
        units = contract.multiplier * contracts
        if contracts <= 0 or covered_shares < units:
            raise ValueError("covered shares must fully cover the short calls")
        _validate_quote(contract, open_quote, opened_at_utc)
        fill = self.fill_policy.fill(open_quote, OrderAction.SELL, opened_at_utc)
        opened, commission, fee, slippage = _trade_event(
            simulation_id=simulation_id,
            event_number=1,
            kind=LifecycleEventKind.OPENED,
            contract=contract,
            contracts=contracts,
            at_utc=opened_at_utc,
            fill=fill,
            action=OrderAction.SELL,
            cost_model=self.cost_model,
        )
        assigned = self.expiration_assignment_hook.should_assign(
            contract, settlement_underlying_price
        )
        if assigned:
            terminal = LifecycleEvent(
                event_id=f"{simulation_id}:2",
                occurred_at_utc=contract.expiration_at_utc,
                kind=LifecycleEventKind.ASSIGNED,
                contract_id=contract.contract_id,
                cashflows=(
                    Cashflow(
                        cashflow_id=f"{simulation_id}:2:assignment",
                        occurred_at_utc=contract.expiration_at_utc,
                        kind=CashflowKind.ASSIGNMENT,
                        amount=contract.strike * units,
                        currency=contract.currency,
                        per_share_amount=contract.strike,
                        per_contract_amount=contract.strike * contract.multiplier,
                        contracts=contracts,
                        multiplier=contract.multiplier,
                        description="physical call assignment sale",
                    ),
                ),
                share_delta=-units,
                details=(f"settlement_underlying_price={settlement_underlying_price}",),
            )
        else:
            terminal = LifecycleEvent(
                event_id=f"{simulation_id}:2",
                occurred_at_utc=contract.expiration_at_utc,
                kind=LifecycleEventKind.EXPIRED_WORTHLESS,
                contract_id=contract.contract_id,
                cashflows=(),
                details=(f"settlement_underlying_price={settlement_underlying_price}",),
            )
        return _result(simulation_id, contract, (opened, terminal), commission, fee, slippage)
