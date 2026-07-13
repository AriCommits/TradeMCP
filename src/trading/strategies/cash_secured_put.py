"""Version 1 reference strategy for 30-45 DTE cash-secured short puts.

The plug-in deliberately keeps market-state inputs separate from its configuration.
Runtime values are carried in ``StrategyContext.parameters`` until a richer strategy
context contract is introduced.  Every market-state input is validated here and a
missing input produces a reject decision rather than an optimistic assumption.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import ceil, isfinite
from typing import Any

from trading.forecasts.targets import ForecastRecord, ForecastTarget
from trading.options.contracts import (
    LegSide,
    OptionLeg,
    OptionType,
    TimeHorizonKind,
)
from trading.portfolio.records import CapitalRequirement, CapitalTreatment
from trading.strategies.base import (
    DataRequirement,
    ForecastRequirement,
    PolicyAction,
    PolicyDecision,
    SizingDecision,
    StrategyContext,
    StrategyRequirements,
)
from trading.strategies.specifications import MarginType, StrategySpecification
from trading.strategies.validation import (
    ParameterField,
    ParameterKind,
    ParameterSchema,
    validate_version,
)


STRATEGY_ID = "cash_secured_put_30_45_dte"
STRATEGY_VERSION = "1.0.0"


def _number(parameters: Mapping[str, Any], name: str) -> float | None:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if isfinite(result) else None


def _short_put(context: StrategyContext) -> OptionLeg | None:
    if len(context.legs) != 1:
        return None
    leg = context.legs[0]
    if leg.side is not LegSide.SHORT or leg.contract.option_type is not OptionType.PUT:
        return None
    return leg


def _calendar_dte(context: StrategyContext, leg: OptionLeg) -> int:
    seconds = (leg.contract.expiration_at_utc - context.decision_at_utc).total_seconds()
    return ceil(seconds / 86_400.0)


def _forecast(
    context: StrategyContext,
    target: ForecastTarget,
    leg: OptionLeg,
) -> ForecastRecord | None:
    bundle = context.forecasts
    if bundle is None or bundle.symbol != leg.contract.underlying:
        return None
    matches: list[ForecastRecord] = []
    for item in bundle.forecasts:
        try:
            model_version = validate_version(item.model_version, field_name="model_version")
        except ValueError:
            continue
        if (
            item.target is target
            and item.horizon.kind is TimeHorizonKind.EXPIRATION_TIMESTAMP
            and item.horizon.end_at_utc == leg.contract.expiration_at_utc
            and item.distribution.point_estimate is not None
            and model_version >= (1, 0, 0)
        ):
            matches.append(item)
    return matches[0] if len(matches) == 1 else None


@dataclass(frozen=True)
class CashSecuredPutEntryPolicy:
    """Apply structural, event, forecast, and risk gates at entry."""

    def evaluate(self, context: StrategyContext) -> PolicyDecision:
        leg = _short_put(context)
        if leg is None:
            return PolicyDecision(PolicyAction.REJECT, ("requires exactly one short put leg",))

        parameters = context.parameters
        reasons: list[str] = []
        dte = _calendar_dte(context, leg)
        min_dte = _number(parameters, "min_dte")
        max_dte = _number(parameters, "max_dte")
        delta = _number(parameters, "option_delta")
        min_delta = _number(parameters, "min_abs_delta")
        max_delta = _number(parameters, "max_abs_delta")
        entry_iv = _number(parameters, "entry_implied_volatility")
        entry_skew = _number(parameters, "entry_put_skew")
        event_flag = parameters.get("has_excluded_event")

        if min_dte is None or max_dte is None or not min_dte <= dte <= max_dte:
            reasons.append("expiration is outside configured 30-45 calendar DTE window")
        if delta is None or min_delta is None or max_delta is None:
            reasons.append("point-in-time option delta is required")
        elif not min_delta <= abs(delta) <= max_delta:
            reasons.append("absolute option delta is outside configured range")
        if entry_iv is None or entry_iv < 0:
            reasons.append("non-negative point-in-time implied volatility is required")
        if entry_skew is None:
            reasons.append("point-in-time put skew is required")
        if not isinstance(event_flag, bool):
            reasons.append("point-in-time earnings/material-event status is required")
        elif event_flag:
            reasons.append("earnings or another excluded material event occurs before expiration")

        required_targets = (
            ForecastTarget.REALIZED_VOLATILITY,
            ForecastTarget.SKEW_CHANGE,
            ForecastTarget.MAX_DOWN_MOVE,
            ForecastTarget.TOUCH_PROBABILITY,
            ForecastTarget.EXPIRATION_ITM_PROBABILITY,
        )
        records = {target: _forecast(context, target, leg) for target in required_targets}
        for target, record in records.items():
            if record is None:
                reasons.append(f"missing unique expiration-matched {target.value} forecast")

        if not reasons:
            assert entry_iv is not None
            realized_vol = records[ForecastTarget.REALIZED_VOLATILITY]
            drawdown = records[ForecastTarget.MAX_DOWN_MOVE]
            touch = records[ForecastTarget.TOUCH_PROBABILITY]
            finish = records[ForecastTarget.EXPIRATION_ITM_PROBABILITY]
            assert realized_vol is not None and realized_vol.distribution.point_estimate is not None
            assert drawdown is not None and drawdown.distribution.point_estimate is not None
            assert touch is not None and touch.distribution.point_estimate is not None
            assert finish is not None and finish.distribution.point_estimate is not None
            if entry_iv - realized_vol.distribution.point_estimate < float(
                parameters["min_volatility_risk_premium"]
            ):
                reasons.append("forecast volatility risk premium is below minimum")
            if drawdown.distribution.point_estimate > float(parameters["max_forecast_drawdown"]):
                reasons.append("forecast drawdown exceeds maximum")
            if touch.distribution.point_estimate > float(parameters["max_touch_probability"]):
                reasons.append("forecast touch probability exceeds maximum")
            if finish.distribution.point_estimate > float(parameters["max_finish_itm_probability"]):
                reasons.append("forecast finish-ITM probability exceeds maximum")
            if finish.distribution.point_estimate > float(parameters["max_assignment_probability"]):
                reasons.append("assignment proxy probability exceeds maximum")

        if reasons:
            return PolicyDecision(PolicyAction.REJECT, tuple(reasons), ("fail_closed",))
        return PolicyDecision(
            PolicyAction.ENTER,
            ("all 30-45 DTE cash-secured-put entry gates passed",),
            ("cash_secured", "earnings_excluded", "assignment_proxy_is_finish_itm"),
        )


@dataclass(frozen=True)
class CashSecuredPutExitPolicy:
    """Close at 50% of credit retained or at 21 DTE by default."""

    def evaluate(self, context: StrategyContext) -> PolicyDecision:
        leg = _short_put(context)
        if leg is None:
            return PolicyDecision(PolicyAction.REJECT, ("requires exactly one short put leg",))
        dte = _calendar_dte(context, leg)
        timed_close = _number(context.parameters, "timed_close_dte")
        if timed_close is None:
            return PolicyDecision(PolicyAction.REJECT, ("timed_close_dte is required",))
        if dte <= timed_close:
            return PolicyDecision(PolicyAction.EXIT, ("configured timed close DTE reached",))

        entry_credit = _number(context.parameters, "entry_credit")
        current_price = _number(context.parameters, "current_option_price")
        target = _number(context.parameters, "profit_target_fraction")
        if entry_credit is None or entry_credit <= 0 or current_price is None or current_price < 0:
            return PolicyDecision(
                PolicyAction.REJECT,
                ("positive entry credit and non-negative current option price are required",),
                ("fail_closed",),
            )
        if target is None:
            return PolicyDecision(PolicyAction.REJECT, ("profit target is required",))
        retained = 1.0 - current_price / entry_credit
        if retained >= target:
            return PolicyDecision(PolicyAction.EXIT, ("configured profit target reached",))
        return PolicyDecision(PolicyAction.HOLD, ("profit and timed-close exits not reached",))


@dataclass(frozen=True)
class NoRollPolicy:
    def evaluate(self, context: StrategyContext) -> PolicyDecision:
        return PolicyDecision(
            PolicyAction.REJECT, ("rolling is disabled in strategy version 1.0.0",)
        )


@dataclass(frozen=True)
class CashSecuredPutSizingPolicy:
    def size(self, context: StrategyContext, *, capital_limit: Decimal) -> SizingDecision:
        leg = _short_put(context)
        max_contracts = _number(context.parameters, "max_contracts")
        if leg is None or max_contracts is None or capital_limit < 0:
            return SizingDecision(0, "missing valid short-put structure, limit, or sizing input")
        per_contract = leg.contract.strike * leg.contract.multiplier
        if per_contract <= 0:
            return SizingDecision(0, "invalid per-contract cash collateral")
        available = min(capital_limit, context.account.cash, context.account.option_buying_power)
        contracts = min(int(max_contracts), int(available // per_contract))
        return SizingDecision(contracts, "full strike collateral reserved per contract")


@dataclass(frozen=True)
class CashSecuredPutCapitalPolicy:
    def requirement(self, context: StrategyContext) -> CapitalRequirement:
        leg = _short_put(context)
        if leg is None:
            return _rejected_capital("requires exactly one short put leg")
        try:
            premium = Decimal(str(context.parameters["entry_credit"]))
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return _rejected_capital("point-in-time entry credit is required")
        if not premium.is_finite() or premium < 0:
            return _rejected_capital("entry credit must be finite and non-negative")
        collateral = leg.contract.strike * leg.contract.multiplier * leg.quantity
        premium_credit = premium * leg.contract.multiplier * leg.quantity
        reasons: list[str] = []
        if collateral > context.account.cash:
            reasons.append("insufficient cash for full strike collateral")
        if collateral > context.account.option_buying_power:
            reasons.append("insufficient option buying power for full strike collateral")
        return CapitalRequirement(
            treatment=CapitalTreatment.CASH_SECURED,
            cash_required=collateral,
            covered_shares_required=Decimal("0"),
            maximum_loss=max(Decimal("0"), collateral - premium_credit),
            estimated_buying_power_reduction=collateral,
            buying_power_is_estimate=True,
            estimate_basis="full strike times multiplier cash collateral; broker-independent",
            opportunity_cost=Decimal("0"),
            eligible=not reasons,
            rejection_reasons=tuple(reasons),
        )


def _rejected_capital(reason: str) -> CapitalRequirement:
    return CapitalRequirement(
        treatment=CapitalTreatment.UNSUPPORTED,
        cash_required=Decimal("0"),
        covered_shares_required=Decimal("0"),
        maximum_loss=Decimal("0"),
        estimated_buying_power_reduction=Decimal("0"),
        buying_power_is_estimate=True,
        estimate_basis="not calculated because strategy inputs failed closed",
        opportunity_cost=Decimal("0"),
        eligible=False,
        rejection_reasons=(reason,),
    )


@dataclass(frozen=True)
class CashSecuredPutStrategy:
    specification: StrategySpecification
    parameter_schema: ParameterSchema
    requirements: StrategyRequirements
    entry_policy: CashSecuredPutEntryPolicy
    exit_policy: CashSecuredPutExitPolicy
    roll_policy: NoRollPolicy
    sizing_policy: CashSecuredPutSizingPolicy
    capital_policy: CashSecuredPutCapitalPolicy


def build_cash_secured_put_strategy(
    parameters: Mapping[str, Any] | None = None,
) -> CashSecuredPutStrategy:
    """Build a deterministic, registration-ready strategy version 1.0.0."""

    fields = {
        "min_dte": ParameterField(ParameterKind.INTEGER, required=False, default=30, minimum=1),
        "max_dte": ParameterField(ParameterKind.INTEGER, required=False, default=45, minimum=1),
        "min_abs_delta": ParameterField(
            ParameterKind.NUMBER, required=False, default=0.15, minimum=0, maximum=1
        ),
        "max_abs_delta": ParameterField(
            ParameterKind.NUMBER, required=False, default=0.30, minimum=0, maximum=1
        ),
        "profit_target_fraction": ParameterField(
            ParameterKind.NUMBER, required=False, default=0.50, minimum=0, maximum=1
        ),
        "timed_close_dte": ParameterField(
            ParameterKind.INTEGER, required=False, default=21, minimum=0
        ),
        "max_contracts": ParameterField(
            ParameterKind.INTEGER, required=False, default=1, minimum=1
        ),
        "min_volatility_risk_premium": ParameterField(
            ParameterKind.NUMBER, required=False, default=0.0, minimum=-2, maximum=2
        ),
        "max_forecast_drawdown": ParameterField(
            ParameterKind.NUMBER, required=False, default=1.0, minimum=0, maximum=1
        ),
        "max_touch_probability": ParameterField(
            ParameterKind.NUMBER, required=False, default=1.0, minimum=0, maximum=1
        ),
        "max_finish_itm_probability": ParameterField(
            ParameterKind.NUMBER, required=False, default=1.0, minimum=0, maximum=1
        ),
        "max_assignment_probability": ParameterField(
            ParameterKind.NUMBER, required=False, default=1.0, minimum=0, maximum=1
        ),
        # Point-in-time values are optional in static configuration, but policies
        # reject when the values needed for the requested decision are absent.
        "option_delta": ParameterField(ParameterKind.NUMBER, required=False, minimum=-1, maximum=1),
        "entry_implied_volatility": ParameterField(
            ParameterKind.NUMBER, required=False, minimum=0, maximum=10
        ),
        "entry_put_skew": ParameterField(
            ParameterKind.NUMBER, required=False, minimum=-10, maximum=10
        ),
        "has_excluded_event": ParameterField(ParameterKind.BOOLEAN, required=False),
        "entry_credit": ParameterField(ParameterKind.NUMBER, required=False, minimum=0),
        "current_option_price": ParameterField(ParameterKind.NUMBER, required=False, minimum=0),
    }
    parameter_schema = ParameterSchema(schema_version=STRATEGY_VERSION, fields=fields)
    normalized_parameters = parameter_schema.validate(parameters or {})
    forecasts = (
        ForecastRequirement(
            ForecastTarget.REALIZED_VOLATILITY, TimeHorizonKind.EXPIRATION_TIMESTAMP, "1.0.0"
        ),
        ForecastRequirement(
            ForecastTarget.SKEW_CHANGE, TimeHorizonKind.EXPIRATION_TIMESTAMP, "1.0.0"
        ),
        ForecastRequirement(
            ForecastTarget.MAX_DOWN_MOVE, TimeHorizonKind.EXPIRATION_TIMESTAMP, "1.0.0"
        ),
        ForecastRequirement(
            ForecastTarget.TOUCH_PROBABILITY, TimeHorizonKind.EXPIRATION_TIMESTAMP, "1.0.0"
        ),
        ForecastRequirement(
            ForecastTarget.EXPIRATION_ITM_PROBABILITY,
            TimeHorizonKind.EXPIRATION_TIMESTAMP,
            "1.0.0",
        ),
    )
    requirements = StrategyRequirements(
        data=(
            DataRequirement.OPTION_CHAIN,
            DataRequirement.UNDERLYING_MARK,
            DataRequirement.ACCOUNT_SNAPSHOT,
            DataRequirement.CORPORATE_EVENTS,
            DataRequirement.DIVIDENDS,
            DataRequirement.RATES,
            DataRequirement.EXCHANGE_CALENDAR,
        ),
        forecasts=forecasts,
    )
    specification = StrategySpecification(
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        family="cash_secured_short_put",
        parameters=normalized_parameters,
        required_forecasts=tuple(sorted(item.target.value for item in forecasts)),
        required_features=tuple(item.value for item in requirements.data),
        allowed_objectives=("expected_pnl", "return_on_collateral", "tail_adjusted_return"),
        supported_margin_types=(
            MarginType.CASH,
            MarginType.REG_T,
            MarginType.PORTFOLIO,
            MarginType.PAPER,
        ),
        known_limitations=(
            "version 1 does not roll positions",
            "expiration ITM probability is the conservative assignment-probability proxy",
            "capital policy reserves full strike collateral and does not use broker margin relief",
        ),
    )
    return CashSecuredPutStrategy(
        specification=specification,
        parameter_schema=parameter_schema,
        requirements=requirements,
        entry_policy=CashSecuredPutEntryPolicy(),
        exit_policy=CashSecuredPutExitPolicy(),
        roll_policy=NoRollPolicy(),
        sizing_policy=CashSecuredPutSizingPolicy(),
        capital_policy=CashSecuredPutCapitalPolicy(),
    )
