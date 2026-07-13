"""Version 1 weekend cash-secured short-put reference strategy.

The strategy sells a put late on Friday and holds it to the next listed
expiration.  Friday's quoted premium is the source of entry proceeds: weekend
theta is already embedded in that market price and is never added as synthetic
P&L.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from trading.candidates.models import (
    CandidateEligibilityPolicy,
    CandidateSelection,
    ScreenedContract,
)
from trading.forecasts.targets import ForecastTarget
from trading.options.contracts import (
    LegSide,
    OptionLeg,
    OptionType,
    TimeHorizonKind,
)
from trading.options.events import MarketEventType
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
from trading.strategies.validation import ParameterField, ParameterKind, ParameterSchema


STRATEGY_ID = "weekend_short_put"
STRATEGY_VERSION = "1.0.0"
_NEW_YORK = ZoneInfo("America/New_York")


def _parameters(values: Mapping[str, Any]) -> dict[str, Any]:
    return WEEKEND_SHORT_PUT_PARAMETER_SCHEMA.validate(values)


def _local_time(value: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("entry-window times must use HH:MM or HH:MM:SS") from exc
    if parsed.tzinfo is not None:
        raise ValueError("entry-window times must be exchange-local wall times")
    return parsed


def _single_short_put(context: StrategyContext) -> OptionLeg | None:
    if len(context.legs) != 1:
        return None
    leg = context.legs[0]
    if leg.side is not LegSide.SHORT or leg.contract.option_type is not OptionType.PUT:
        return None
    return leg


def _missing_forecasts(context: StrategyContext, expiration_at_utc: datetime) -> tuple[str, ...]:
    if context.forecasts is None:
        return tuple(item.target.value for item in WEEKEND_SHORT_PUT_REQUIREMENTS.forecasts)
    available = {
        (record.target, record.horizon.kind, record.horizon.end_at_utc)
        for record in context.forecasts.forecasts
    }
    missing: list[str] = []
    for requirement in WEEKEND_SHORT_PUT_REQUIREMENTS.forecasts:
        if requirement.horizon_kind is TimeHorizonKind.EXPIRATION_TIMESTAMP:
            key = (requirement.target, requirement.horizon_kind, expiration_at_utc)
            present = key in available
        else:
            present = any(
                target is requirement.target and kind is requirement.horizon_kind
                for target, kind, _ in available
            )
        if not present:
            missing.append(requirement.target.value)
    return tuple(missing)


class WeekendShortPutEntryPolicy:
    """Fail-closed Friday-window and forecast-completeness policy."""

    def evaluate(self, context: StrategyContext) -> PolicyDecision:
        leg = _single_short_put(context)
        if leg is None:
            return PolicyDecision(PolicyAction.REJECT, ("requires_exactly_one_short_put",))
        params = _parameters(context.parameters)
        local = context.decision_at_utc.astimezone(_NEW_YORK)
        start = _local_time(str(params["entry_start_local"]))
        end = _local_time(str(params["entry_end_local"]))
        if start > end:
            return PolicyDecision(PolicyAction.REJECT, ("entry_window_is_inverted",))
        if local.weekday() != 4:
            return PolicyDecision(PolicyAction.REJECT, ("entry_is_not_friday_new_york",))
        if not start <= local.time().replace(tzinfo=None) <= end:
            return PolicyDecision(PolicyAction.REJECT, ("outside_friday_entry_window",))
        if leg.contract.expiration_at_utc <= context.decision_at_utc:
            return PolicyDecision(PolicyAction.REJECT, ("expiration_is_not_after_entry",))
        missing = _missing_forecasts(context, leg.contract.expiration_at_utc)
        if missing:
            return PolicyDecision(
                PolicyAction.REJECT,
                tuple(f"missing_forecast:{name}" for name in missing),
            )
        return PolicyDecision(
            PolicyAction.ENTER,
            ("friday_window_and_required_inputs_satisfied",),
            ("premium_is_market_quote_no_synthetic_weekend_theta",),
        )


class WeekendShortPutExitPolicy:
    """Version 1 deliberately holds through expiration without a profit target."""

    def evaluate(self, context: StrategyContext) -> PolicyDecision:
        leg = _single_short_put(context)
        if leg is None:
            return PolicyDecision(PolicyAction.REJECT, ("requires_exactly_one_short_put",))
        if context.decision_at_utc < leg.contract.expiration_at_utc:
            return PolicyDecision(PolicyAction.HOLD, ("hold_to_expiration_v1",))
        return PolicyDecision(PolicyAction.EXIT, ("expiration_reached",))


class WeekendShortPutRollPolicy:
    def evaluate(self, context: StrategyContext) -> PolicyDecision:
        return PolicyDecision(PolicyAction.REJECT, ("rolling_not_supported_in_v1",))


class WeekendShortPutSizingPolicy:
    """Size from the most restrictive cash-secured account limit."""

    def size(self, context: StrategyContext, *, capital_limit: Decimal) -> SizingDecision:
        leg = _single_short_put(context)
        if leg is None or capital_limit < 0:
            return SizingDecision(0, "invalid_short_put_or_capital_limit")
        params = _parameters(context.parameters)
        collateral = leg.contract.strike * leg.contract.multiplier
        account_fraction_limit = context.account.net_liquidation * Decimal(
            str(params["maximum_account_fraction"])
        )
        available = min(
            capital_limit,
            context.account.cash,
            context.account.option_buying_power,
            account_fraction_limit,
        )
        count = int((available / collateral).to_integral_value(rounding=ROUND_FLOOR))
        count = min(count, int(params["max_contracts"]))
        return SizingDecision(max(0, count), "cash_secured_collateral_limit")


class WeekendShortPutCapitalPolicy:
    """Portable cash-secured requirement; broker buying power remains an estimate."""

    def requirement(self, context: StrategyContext) -> CapitalRequirement:
        leg = _single_short_put(context)
        if leg is None:
            return _unsupported_capital("requires exactly one short put")
        collateral = leg.contract.strike * leg.contract.multiplier * leg.quantity
        quoted_credit = (leg.limit_price or Decimal("0")) * leg.contract.multiplier * leg.quantity
        reasons: list[str] = []
        if context.account.margin_type not in (MarginType.CASH, MarginType.PAPER):
            reasons.append("cash or paper account required")
        if collateral > context.account.cash:
            reasons.append("insufficient cash")
        if collateral > context.account.option_buying_power:
            reasons.append("insufficient option buying power")
        return CapitalRequirement(
            treatment=CapitalTreatment.CASH_SECURED,
            cash_required=collateral,
            covered_shares_required=Decimal("0"),
            maximum_loss=max(Decimal("0"), collateral - quoted_credit),
            estimated_buying_power_reduction=collateral,
            buying_power_is_estimate=True,
            estimate_basis="full strike times multiplier cash collateral; broker-independent estimate",
            opportunity_cost=Decimal("0"),
            eligible=not reasons,
            rejection_reasons=tuple(reasons),
        )


def _unsupported_capital(reason: str) -> CapitalRequirement:
    return CapitalRequirement(
        treatment=CapitalTreatment.UNSUPPORTED,
        cash_required=Decimal("0"),
        covered_shares_required=Decimal("0"),
        maximum_loss=Decimal("0"),
        estimated_buying_power_reduction=Decimal("0"),
        buying_power_is_estimate=True,
        estimate_basis="not calculated because the candidate is not a cash-secured short put",
        opportunity_cost=Decimal("0"),
        eligible=False,
        rejection_reasons=(reason,),
    )


WEEKEND_SHORT_PUT_PARAMETER_SCHEMA = ParameterSchema(
    schema_version=STRATEGY_VERSION,
    fields={
        "entry_end_local": ParameterField(ParameterKind.STRING, required=False, default="15:55"),
        "entry_start_local": ParameterField(ParameterKind.STRING, required=False, default="15:30"),
        "max_contracts": ParameterField(
            ParameterKind.INTEGER, required=False, default=1, minimum=1
        ),
        "maximum_account_fraction": ParameterField(
            ParameterKind.NUMBER, required=False, default=0.05, minimum=0.0, maximum=1.0
        ),
        "maximum_absolute_delta": ParameterField(
            ParameterKind.NUMBER, required=False, default=0.30, minimum=0.0, maximum=1.0
        ),
        "maximum_relative_spread": ParameterField(
            ParameterKind.NUMBER, required=False, default=0.20, minimum=0.0
        ),
        "minimum_absolute_delta": ParameterField(
            ParameterKind.NUMBER, required=False, default=0.15, minimum=0.0, maximum=1.0
        ),
        "minimum_open_interest": ParameterField(
            ParameterKind.INTEGER, required=False, default=100, minimum=0
        ),
    },
)


WEEKEND_SHORT_PUT_REQUIREMENTS = StrategyRequirements(
    data=(
        DataRequirement.OPTION_CHAIN,
        DataRequirement.UNDERLYING_MARK,
        DataRequirement.ACCOUNT_SNAPSHOT,
        DataRequirement.CORPORATE_EVENTS,
        DataRequirement.DIVIDENDS,
        DataRequirement.EXCHANGE_CALENDAR,
    ),
    forecasts=(
        ForecastRequirement(ForecastTarget.GAP_RETURN, TimeHorizonKind.OVERNIGHT_INTERVALS),
        ForecastRequirement(ForecastTarget.TOUCH_PROBABILITY, TimeHorizonKind.EXPIRATION_TIMESTAMP),
        ForecastRequirement(
            ForecastTarget.EXPIRATION_ITM_PROBABILITY,
            TimeHorizonKind.EXPIRATION_TIMESTAMP,
        ),
        ForecastRequirement(
            ForecastTarget.REALIZED_VOLATILITY, TimeHorizonKind.EXPIRATION_TIMESTAMP
        ),
        ForecastRequirement(ForecastTarget.IV_CHANGE, TimeHorizonKind.EXPIRATION_TIMESTAMP),
        ForecastRequirement(ForecastTarget.BID_ASK_SPREAD, TimeHorizonKind.EXPIRATION_TIMESTAMP),
    ),
)


@dataclass(frozen=True)
class WeekendShortPutStrategy:
    specification: StrategySpecification = StrategySpecification(
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        family="cash_secured_short_put",
        parameters=WEEKEND_SHORT_PUT_PARAMETER_SCHEMA.validate({}),
        required_forecasts=tuple(
            sorted({item.target.value for item in WEEKEND_SHORT_PUT_REQUIREMENTS.forecasts})
        ),
        required_features=tuple(item.value for item in WEEKEND_SHORT_PUT_REQUIREMENTS.data),
        allowed_objectives=("expected_pnl", "return_on_capital", "tail_adjusted_return"),
        supported_margin_types=(MarginType.CASH, MarginType.PAPER),
        known_limitations=(
            "version 1 holds to expiration and does not roll",
            "expiration ITM probability is the assignment-risk input",
            "weekend theta is already embedded in Friday premium and is never added to P&L",
        ),
    )
    parameter_schema: ParameterSchema = WEEKEND_SHORT_PUT_PARAMETER_SCHEMA
    requirements: StrategyRequirements = WEEKEND_SHORT_PUT_REQUIREMENTS
    entry_policy: WeekendShortPutEntryPolicy = WeekendShortPutEntryPolicy()
    exit_policy: WeekendShortPutExitPolicy = WeekendShortPutExitPolicy()
    roll_policy: WeekendShortPutRollPolicy = WeekendShortPutRollPolicy()
    sizing_policy: WeekendShortPutSizingPolicy = WeekendShortPutSizingPolicy()
    capital_policy: WeekendShortPutCapitalPolicy = WeekendShortPutCapitalPolicy()

    def candidate_selection(self, decision_at_utc: datetime) -> CandidateSelection:
        """Select puts after entry; ``next_expiration_candidates`` narrows to the first listing."""

        return CandidateSelection(
            option_types=(OptionType.PUT,), earliest_expiration_at_utc=decision_at_utc
        )

    def eligibility_policy(
        self, parameters: Mapping[str, Any] | None = None
    ) -> CandidateEligibilityPolicy:
        params = _parameters(parameters or {})
        return CandidateEligibilityPolicy(
            maximum_relative_spread=Decimal(str(params["maximum_relative_spread"])),
            minimum_open_interest=int(params["minimum_open_interest"]),
            require_event_calendar=True,
            blocked_event_types=(
                MarketEventType.EARNINGS,
                MarketEventType.ECONOMIC_RELEASE,
                MarketEventType.CENTRAL_BANK,
                MarketEventType.REGULATORY,
            ),
            require_account_and_capabilities=True,
            required_leg_count=1,
            require_capital_estimate=True,
        )

    def next_expiration_candidates(
        self,
        candidates: tuple[ScreenedContract, ...],
        *,
        absolute_delta_by_contract: Mapping[str, float],
        parameters: Mapping[str, Any] | None = None,
    ) -> tuple[ScreenedContract, ...]:
        """Return eligible puts at the nearest listed future expiration.

        Delta is supplemental point-in-time model output and must be present for
        every otherwise eligible put.  Missing delta fails closed.
        """

        params = _parameters(parameters or {})
        lower = float(params["minimum_absolute_delta"])
        upper = float(params["maximum_absolute_delta"])
        if lower > upper:
            raise ValueError("minimum_absolute_delta cannot exceed maximum_absolute_delta")
        eligible_puts = tuple(
            candidate
            for candidate in candidates
            if candidate.eligible
            and candidate.contract.option_type is OptionType.PUT
            and candidate.contract.expiration_at_utc > candidate.decision_at_utc
        )
        if not eligible_puts:
            return ()
        next_expiration = min(item.contract.expiration_at_utc for item in eligible_puts)
        nearest = tuple(
            candidate
            for candidate in eligible_puts
            if candidate.contract.expiration_at_utc == next_expiration
        )

        filtered: list[ScreenedContract] = []
        for candidate in nearest:
            if candidate.contract.contract_id not in absolute_delta_by_contract:
                raise ValueError(
                    f"missing point-in-time delta for {candidate.contract.contract_id}"
                )
            delta = abs(float(absolute_delta_by_contract[candidate.contract.contract_id]))
            if lower <= delta <= upper:
                filtered.append(candidate)
        return tuple(
            sorted(
                filtered,
                key=lambda item: (item.contract.strike, item.contract.contract_id),
            )
        )


WEEKEND_SHORT_PUT = WeekendShortPutStrategy()


def build_weekend_short_put_strategy(
    parameters: Mapping[str, Any] | None = None,
) -> WeekendShortPutStrategy:
    """Build a registry-compatible plug-in with normalized, versioned parameters."""

    normalized = WEEKEND_SHORT_PUT_PARAMETER_SCHEMA.validate(parameters or {})
    return replace(
        WEEKEND_SHORT_PUT,
        specification=replace(WEEKEND_SHORT_PUT.specification, parameters=normalized),
    )
