"""Deterministic option-chain enumeration and eligibility gates."""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal

from trading.options.contracts import OptionContract, require_utc
from trading.options.events import EventCalendarSnapshot
from trading.options.quotes import OptionChainSnapshot, OptionQuote, QuoteQualityFlag

from .models import (
    CandidateEligibilityContext,
    CandidateEligibilityPolicy,
    CandidateRejectionCode,
    CandidateSelection,
    ContractActivity,
    ScreenedContract,
)


_REASON_RANK = {reason: rank for rank, reason in enumerate(CandidateRejectionCode)}


def _candidate_key(chain_id: str, strategy_id: str, strategy_version: str, contract_id: str) -> str:
    payload = "\x1f".join((chain_id, strategy_id, strategy_version, contract_id))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _contract_sort_key(contract: OptionContract) -> tuple[datetime, Decimal, str, str]:
    return (
        contract.expiration_at_utc,
        contract.strike,
        contract.option_type.value,
        contract.contract_id,
    )


def _selected(contract: OptionContract, selection: CandidateSelection) -> bool:
    if contract.option_type not in selection.option_types:
        return False
    if (
        selection.earliest_expiration_at_utc is not None
        and contract.expiration_at_utc < selection.earliest_expiration_at_utc
    ):
        return False
    if (
        selection.latest_expiration_at_utc is not None
        and contract.expiration_at_utc > selection.latest_expiration_at_utc
    ):
        return False
    if selection.minimum_strike is not None and contract.strike < selection.minimum_strike:
        return False
    return selection.maximum_strike is None or contract.strike <= selection.maximum_strike


def _quote_for(contract_id: str, quotes: tuple[OptionQuote, ...]) -> OptionQuote | None:
    matches = (quote for quote in quotes if quote.contract_id == contract_id)
    return max(
        matches,
        key=lambda quote: (
            quote.as_of_utc,
            quote.ingested_at_utc,
            quote.source,
            quote.source_record_id or "",
            quote.to_json(),
        ),
        default=None,
    )


def _quote_reasons(
    quote: OptionQuote | None,
    decision_at_utc: datetime,
    policy: CandidateEligibilityPolicy,
) -> set[CandidateRejectionCode]:
    if quote is None:
        return {CandidateRejectionCode.QUOTE_MISSING}
    reasons: set[CandidateRejectionCode] = set()
    if quote.as_of_utc > decision_at_utc or quote.ingested_at_utc > decision_at_utc:
        reasons.add(CandidateRejectionCode.QUOTE_FROM_FUTURE)
    elif decision_at_utc - quote.as_of_utc > policy.max_quote_age:
        reasons.add(CandidateRejectionCode.QUOTE_STALE)
    flags = set(quote.quality_flags)
    if quote.ask < quote.bid or QuoteQualityFlag.CROSSED in flags:
        reasons.add(CandidateRejectionCode.QUOTE_CROSSED)
    if quote.ask == quote.bid or QuoteQualityFlag.LOCKED in flags:
        if policy.reject_locked_quotes:
            reasons.add(CandidateRejectionCode.QUOTE_LOCKED)
    if quote.bid == 0 or QuoteQualityFlag.ZERO_BID in flags:
        if policy.reject_zero_bid:
            reasons.add(CandidateRejectionCode.QUOTE_ZERO_BID)
    if quote.bid_size is None or quote.ask_size is None or QuoteQualityFlag.MISSING_SIZE in flags:
        if policy.require_quote_sizes:
            reasons.add(CandidateRejectionCode.QUOTE_MISSING_SIZE)
    spread = quote.ask - quote.bid
    if policy.maximum_absolute_spread is not None and spread > policy.maximum_absolute_spread:
        reasons.add(CandidateRejectionCode.ABSOLUTE_SPREAD_EXCEEDED)
    midpoint = quote.midpoint
    if policy.maximum_relative_spread is not None and (
        midpoint <= 0 or spread / midpoint > policy.maximum_relative_spread
    ):
        reasons.add(CandidateRejectionCode.RELATIVE_SPREAD_EXCEEDED)
    return reasons


def _activity_reasons(
    activity: ContractActivity | None,
    decision_at_utc: datetime,
    policy: CandidateEligibilityPolicy,
) -> set[CandidateRejectionCode]:
    needs_activity = (
        policy.minimum_volume > 0
        or policy.minimum_open_interest > 0
        or policy.require_capital_estimate
    )
    if activity is None:
        return {CandidateRejectionCode.ACTIVITY_MISSING} if needs_activity else set()
    reasons: set[CandidateRejectionCode] = set()
    if activity.as_of_utc > decision_at_utc:
        reasons.add(CandidateRejectionCode.ACTIVITY_FROM_FUTURE)
        return reasons
    if decision_at_utc - activity.as_of_utc > policy.max_activity_age:
        reasons.add(CandidateRejectionCode.ACTIVITY_STALE)
    if policy.minimum_volume > 0:
        if activity.volume is None:
            reasons.add(CandidateRejectionCode.ACTIVITY_MISSING)
        elif activity.volume < policy.minimum_volume:
            reasons.add(CandidateRejectionCode.VOLUME_BELOW_MINIMUM)
    if policy.minimum_open_interest > 0:
        if activity.open_interest is None:
            reasons.add(CandidateRejectionCode.ACTIVITY_MISSING)
        elif activity.open_interest < policy.minimum_open_interest:
            reasons.add(CandidateRejectionCode.OPEN_INTEREST_BELOW_MINIMUM)
    if policy.require_capital_estimate and activity.required_option_buying_power is None:
        reasons.add(CandidateRejectionCode.CAPITAL_REQUIREMENT_MISSING)
    return reasons


def _event_reasons(
    calendar: EventCalendarSnapshot | None,
    contract: OptionContract,
    decision_at_utc: datetime,
    policy: CandidateEligibilityPolicy,
) -> set[CandidateRejectionCode]:
    if calendar is None:
        return (
            {CandidateRejectionCode.EVENT_CALENDAR_MISSING}
            if policy.require_event_calendar
            else set()
        )
    reasons: set[CandidateRejectionCode] = set()
    if calendar.as_of_utc > decision_at_utc:
        reasons.add(CandidateRejectionCode.EVENT_CALENDAR_FROM_FUTURE)
        return reasons
    elif decision_at_utc - calendar.as_of_utc > policy.max_event_calendar_age:
        reasons.add(CandidateRejectionCode.EVENT_CALENDAR_STALE)
    if (
        decision_at_utc < calendar.covered_from_utc
        or contract.expiration_at_utc > calendar.covered_through_utc
    ):
        reasons.add(CandidateRejectionCode.EVENT_COVERAGE_MISSING)
        return reasons
    blocked_types = set(policy.blocked_event_types)
    if blocked_types and any(
        event.event_type in blocked_types
        and decision_at_utc <= event.effective_at_utc <= contract.expiration_at_utc
        and event.symbol in (None, contract.underlying)
        for event in calendar.events
    ):
        reasons.add(CandidateRejectionCode.BLOCKED_EVENT)
    return reasons


def _account_reasons(
    context: CandidateEligibilityContext,
    activity: ContractActivity | None,
    decision_at_utc: datetime,
    policy: CandidateEligibilityPolicy,
) -> set[CandidateRejectionCode]:
    if not policy.require_account_and_capabilities:
        return set()
    account = context.account
    capabilities = context.broker_capabilities
    reasons: set[CandidateRejectionCode] = set()
    if account is None:
        reasons.add(CandidateRejectionCode.ACCOUNT_MISSING)
    else:
        if account.as_of_utc > decision_at_utc:
            reasons.add(CandidateRejectionCode.ACCOUNT_FROM_FUTURE)
            account = None
        elif decision_at_utc - account.as_of_utc > policy.max_account_age:
            reasons.add(CandidateRejectionCode.ACCOUNT_STALE)
    if capabilities is None:
        reasons.add(CandidateRejectionCode.BROKER_CAPABILITIES_MISSING)
        return reasons
    if capabilities.as_of_utc > decision_at_utc or capabilities.published_at_utc > decision_at_utc:
        reasons.add(CandidateRejectionCode.BROKER_CAPABILITIES_FROM_FUTURE)
        return reasons
    elif decision_at_utc - capabilities.as_of_utc > policy.max_capability_age:
        reasons.add(CandidateRejectionCode.BROKER_CAPABILITIES_STALE)
    if account is None:
        return reasons
    if account.adapter != capabilities.adapter:
        reasons.add(CandidateRejectionCode.BROKER_ADAPTER_MISMATCH)
    if not capabilities.supports_equity_options:
        reasons.add(CandidateRejectionCode.EQUITY_OPTIONS_UNSUPPORTED)
    if not capabilities.supports(account.margin_type, account.option_level):
        reasons.add(CandidateRejectionCode.ACCOUNT_OPTION_LEVEL_UNSUPPORTED)
    if policy.required_leg_count > 1 and not capabilities.supports_multi_leg:
        reasons.add(CandidateRejectionCode.MULTI_LEG_UNSUPPORTED)
    if activity is not None and activity.required_option_buying_power is not None:
        if activity.required_option_buying_power > account.option_buying_power:
            reasons.add(CandidateRejectionCode.INSUFFICIENT_OPTION_BUYING_POWER)
    return reasons


def screen_option_candidates(
    chain: OptionChainSnapshot,
    *,
    decision_at_utc: datetime,
    strategy_id: str,
    strategy_version: str,
    selection: CandidateSelection | None = None,
    policy: CandidateEligibilityPolicy | None = None,
    context: CandidateEligibilityContext | None = None,
) -> tuple[ScreenedContract, ...]:
    """Enumerate and screen contracts without discarding rejected alternatives."""

    require_utc(decision_at_utc, "decision_at_utc")
    if not strategy_id or not strategy_version:
        raise ValueError("strategy_id and strategy_version are required")
    selection = selection or CandidateSelection()
    policy = policy or CandidateEligibilityPolicy()
    context = context or CandidateEligibilityContext()
    snapshot_reasons: set[CandidateRejectionCode] = set()
    if chain.as_of_utc > decision_at_utc or chain.ingested_at_utc > decision_at_utc:
        snapshot_reasons.add(CandidateRejectionCode.SNAPSHOT_FROM_FUTURE)
    elif decision_at_utc - chain.as_of_utc > policy.max_snapshot_age:
        snapshot_reasons.add(CandidateRejectionCode.SNAPSHOT_STALE)

    results: list[ScreenedContract] = []
    contracts = sorted(
        (contract for contract in chain.contracts if _selected(contract, selection)),
        key=_contract_sort_key,
    )
    for contract in contracts:
        quote = _quote_for(contract.contract_id, chain.quotes)
        activity = context.activity_by_contract.get(contract.contract_id)
        reasons = set(snapshot_reasons)
        if contract.expiration_at_utc <= decision_at_utc:
            reasons.add(CandidateRejectionCode.CONTRACT_EXPIRED)
        reasons.update(_quote_reasons(quote, decision_at_utc, policy))
        reasons.update(_activity_reasons(activity, decision_at_utc, policy))
        reasons.update(_event_reasons(context.event_calendar, contract, decision_at_utc, policy))
        reasons.update(_account_reasons(context, activity, decision_at_utc, policy))
        ordered_reasons = tuple(sorted(reasons, key=_REASON_RANK.__getitem__))
        results.append(
            ScreenedContract(
                candidate_key=_candidate_key(
                    chain.chain_id, strategy_id, strategy_version, contract.contract_id
                ),
                chain_id=chain.chain_id,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                decision_at_utc=decision_at_utc,
                contract=contract,
                quote=quote,
                activity=activity,
                eligible=not ordered_reasons,
                rejection_reasons=ordered_reasons,
            )
        )
    return tuple(results)
