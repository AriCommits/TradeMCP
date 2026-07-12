"""Capital requirements and account eligibility for option positions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from math import ceil

from trading.accounts.records import BrokerCapabilities
from trading.options.contracts import LegSide, OptionLeg, OptionType, require_utc
from trading.strategies.specifications import AccountSnapshot

from .records import CapitalRequirement, CapitalTreatment


def _premium(leg: OptionLeg, prices: Mapping[str, Decimal]) -> Decimal:
    try:
        price = prices[leg.contract.contract_id]
    except KeyError as exc:
        raise ValueError(f"missing option price for {leg.contract.contract_id}") from exc
    if price < 0:
        raise ValueError("option prices cannot be negative")
    return price * leg.contract.multiplier * leg.quantity


def _net_debit(legs: Sequence[OptionLeg], prices: Mapping[str, Decimal]) -> Decimal:
    debit = Decimal("0")
    for leg in legs:
        amount = _premium(leg, prices)
        debit += amount if leg.side is LegSide.LONG else -amount
    return debit


def _opportunity_cost(capital: Decimal, annual_rate: Decimal, days: int) -> Decimal:
    if annual_rate < 0:
        raise ValueError("opportunity cost rate cannot be negative")
    if days < 0:
        raise ValueError("holding period cannot be negative")
    return capital * annual_rate * Decimal(days) / Decimal("365")


def _covered_shares(account: AccountSnapshot, symbol: str) -> Decimal:
    return sum(
        (
            holding.quantity
            for holding in account.holdings
            if holding.asset_id == symbol
            and holding.asset_kind == "equity"
            and holding.quantity > 0
        ),
        start=Decimal("0"),
    )


def _covered_share_value(
    account: AccountSnapshot,
    symbol: str,
    required_shares: Decimal,
) -> Decimal:
    remaining = required_shares
    value = Decimal("0")
    for holding in account.holdings:
        if holding.asset_id != symbol or holding.asset_kind != "equity" or holding.quantity <= 0:
            continue
        if holding.mark_price is None:
            raise ValueError("covered equity holding requires a mark price")
        used = min(remaining, holding.quantity)
        value += used * holding.mark_price
        remaining -= used
        if remaining == 0:
            break
    if remaining > 0:
        raise ValueError("insufficient covered shares")
    return value


def _defined_risk_maximum_loss(
    legs: Sequence[OptionLeg], prices: Mapping[str, Decimal]
) -> Decimal | None:
    if len(legs) != 2:
        return None
    left, right = legs
    same_series = (
        left.contract.underlying == right.contract.underlying
        and left.contract.option_type is right.contract.option_type
        and left.contract.expiration_at_utc == right.contract.expiration_at_utc
        and left.contract.exercise_style is right.contract.exercise_style
        and left.contract.settlement_type is right.contract.settlement_type
        and left.quantity == right.quantity
        and left.side is not right.side
        and left.contract.multiplier == right.contract.multiplier
    )
    if not same_series:
        return None
    test_spots = (
        Decimal("0"),
        left.contract.strike,
        right.contract.strike,
        max(left.contract.strike, right.contract.strike) * 2,
    )
    payoffs: list[Decimal] = []
    for spot in test_spots:
        payoff = Decimal("0")
        for leg in legs:
            if leg.contract.option_type is OptionType.CALL:
                intrinsic = max(Decimal("0"), spot - leg.contract.strike)
            else:
                intrinsic = max(Decimal("0"), leg.contract.strike - spot)
            sign = Decimal("1") if leg.side is LegSide.LONG else Decimal("-1")
            payoff += sign * intrinsic * leg.contract.multiplier * leg.quantity
        payoffs.append(payoff)
    return max(Decimal("0"), _net_debit(legs, prices) - min(payoffs))


def calculate_capital_requirement(
    legs: Sequence[OptionLeg],
    *,
    account: AccountSnapshot,
    capabilities: BrokerCapabilities,
    option_prices: Mapping[str, Decimal],
    decision_at_utc: datetime,
    annual_opportunity_rate: Decimal = Decimal("0"),
    max_account_age: timedelta = timedelta(minutes=1),
    max_capability_age: timedelta = timedelta(days=1),
) -> CapitalRequirement:
    """Calculate conservative capital and fail closed on unsupported inputs.

    The buying-power number is a portable estimate, not a broker quote. Naked
    option positions are deliberately unsupported in this research baseline.
    """

    require_utc(decision_at_utc, "decision_at_utc")
    if not legs:
        raise ValueError("at least one option leg is required")
    if max_account_age < timedelta(0) or max_capability_age < timedelta(0):
        raise ValueError("freshness limits cannot be negative")
    if account.adapter != capabilities.adapter:
        raise ValueError("account and broker capability adapters do not match")
    if account.as_of_utc > decision_at_utc:
        raise ValueError("account snapshot cannot be from the future")
    if decision_at_utc - account.as_of_utc > max_account_age:
        raise ValueError("account snapshot is stale")
    if capabilities.as_of_utc > decision_at_utc or capabilities.published_at_utc > decision_at_utc:
        raise ValueError("broker capabilities cannot be from the future")
    if decision_at_utc - capabilities.as_of_utc > max_capability_age:
        raise ValueError("broker capabilities are stale")
    if not capabilities.supports(account.margin_type, account.option_level):
        return _rejected("account option level or margin type is not supported")
    if len(legs) > 1 and not capabilities.supports_multi_leg:
        return _rejected("broker does not support multi-leg options")
    currencies = {leg.contract.currency for leg in legs}
    if currencies != {account.currency}:
        raise ValueError("option and account currencies must match")

    net_debit = _net_debit(legs, option_prices)
    expirations = {leg.contract.expiration_at_utc for leg in legs}
    if any(expiry <= decision_at_utc for expiry in expirations):
        raise ValueError("cannot calculate capital for an expired option")
    holding_days = max(
        ceil((expiry - decision_at_utc).total_seconds() / 86_400.0) for expiry in expirations
    )

    defined_risk_loss = _defined_risk_maximum_loss(legs, option_prices)
    if defined_risk_loss is not None:
        maximum_loss = defined_risk_loss
        cash = max(Decimal("0"), net_debit)
        capital = maximum_loss
        return _result(
            CapitalTreatment.DEFINED_RISK,
            cash,
            Decimal("0"),
            maximum_loss,
            capital,
            annual_opportunity_rate,
            holding_days,
            account,
        )

    if all(leg.side is LegSide.LONG for leg in legs):
        if net_debit < 0:
            raise ValueError("long-only position cannot produce a net credit")
        return _result(
            CapitalTreatment.DEBIT_PAID,
            net_debit,
            Decimal("0"),
            net_debit,
            net_debit,
            annual_opportunity_rate,
            holding_days,
            account,
        )

    if len(legs) == 1:
        leg = legs[0]
        premium_credit = max(Decimal("0"), -net_debit)
        if leg.side is LegSide.SHORT and leg.contract.option_type is OptionType.PUT:
            collateral = leg.contract.strike * leg.contract.multiplier * leg.quantity
            maximum_loss = max(Decimal("0"), collateral - premium_credit)
            return _result(
                CapitalTreatment.CASH_SECURED,
                collateral,
                Decimal("0"),
                maximum_loss,
                collateral,
                annual_opportunity_rate,
                holding_days,
                account,
            )
        if leg.side is LegSide.SHORT and leg.contract.option_type is OptionType.CALL:
            shares = leg.contract.multiplier * leg.quantity
            available = _covered_shares(account, leg.contract.underlying)
            reasons = () if available >= shares else ("insufficient covered shares",)
            covered_value = (
                _covered_share_value(account, leg.contract.underlying, shares)
                if not reasons
                else Decimal("0")
            )
            maximum_loss = max(Decimal("0"), covered_value - premium_credit)
            return CapitalRequirement(
                treatment=CapitalTreatment.COVERED_SHARES,
                cash_required=Decimal("0"),
                covered_shares_required=shares,
                maximum_loss=maximum_loss,
                estimated_buying_power_reduction=Decimal("0"),
                buying_power_is_estimate=True,
                estimate_basis=(
                    "covered-share requirement; maximum loss uses current marked share value"
                ),
                opportunity_cost=_opportunity_cost(
                    covered_value, annual_opportunity_rate, holding_days
                ),
                eligible=not reasons,
                rejection_reasons=reasons,
            )

    return _rejected("naked or unsupported option structure")


def _result(
    treatment: CapitalTreatment,
    cash: Decimal,
    shares: Decimal,
    maximum_loss: Decimal,
    estimated_bpr: Decimal,
    rate: Decimal,
    holding_days: int,
    account: AccountSnapshot,
) -> CapitalRequirement:
    reasons: list[str] = []
    if cash > account.cash:
        reasons.append("insufficient cash")
    if estimated_bpr > account.option_buying_power:
        reasons.append("insufficient option buying power")
    return CapitalRequirement(
        treatment=treatment,
        cash_required=cash,
        covered_shares_required=shares,
        maximum_loss=maximum_loss,
        estimated_buying_power_reduction=estimated_bpr,
        buying_power_is_estimate=True,
        estimate_basis="broker-independent conservative maximum-loss estimate",
        opportunity_cost=_opportunity_cost(estimated_bpr, rate, holding_days),
        eligible=not reasons,
        rejection_reasons=tuple(reasons),
    )


def _rejected(reason: str) -> CapitalRequirement:
    return CapitalRequirement(
        treatment=CapitalTreatment.UNSUPPORTED,
        cash_required=Decimal("0"),
        covered_shares_required=Decimal("0"),
        maximum_loss=Decimal("0"),
        estimated_buying_power_reduction=Decimal("0"),
        buying_power_is_estimate=True,
        estimate_basis="not calculated because eligibility checks failed",
        opportunity_cost=Decimal("0"),
        eligible=False,
        rejection_reasons=(reason,),
    )
