from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trading.accounts.records import BrokerCapabilities
from trading.candidates import (
    CandidateEligibilityContext,
    CandidateEligibilityPolicy,
    CandidateRejectionCode,
    CandidateSelection,
    ContractActivity,
    ScreenedContract,
    screen_option_candidates,
)
from trading.options.contracts import (
    ExerciseStyle,
    OptionContract,
    OptionType,
    SettlementType,
)
from trading.options.events import (
    EventCalendarSnapshot,
    MarketEvent,
    MarketEventType,
)
from trading.options.quotes import OptionChainSnapshot, OptionQuote, QuoteQualityFlag
from trading.strategies.specifications import AccountSnapshot, MarginType


UTC = timezone.utc
DECISION = datetime(2026, 7, 10, 20, 0, tzinfo=UTC)
EXPIRATION = datetime(2026, 7, 13, 20, 0, tzinfo=UTC)


def contract(
    contract_id: str,
    strike: str,
    *,
    option_type: OptionType = OptionType.PUT,
    expiration_at_utc: datetime = EXPIRATION,
) -> OptionContract:
    return OptionContract(
        contract_id=contract_id,
        occ_symbol=f"SPY-{contract_id}",
        underlying="SPY",
        option_type=option_type,
        strike=Decimal(strike),
        expiration_date=expiration_at_utc.date(),
        expiration_at_utc=expiration_at_utc,
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=SettlementType.PHYSICAL,
    )


def quote(
    contract_id: str,
    bid: str = "1.00",
    ask: str = "1.10",
    *,
    as_of_utc: datetime = DECISION - timedelta(seconds=30),
    flags: tuple[QuoteQualityFlag, ...] = (),
    bid_size: int | None = 10,
    ask_size: int | None = 12,
) -> OptionQuote:
    return OptionQuote(
        contract_id=contract_id,
        as_of_utc=as_of_utc,
        bid=Decimal(bid),
        ask=Decimal(ask),
        bid_size=bid_size,
        ask_size=ask_size,
        underlying_price=Decimal("600"),
        source="test",
        ingested_at_utc=as_of_utc,
        quality_flags=flags,
    )


def chain(
    contracts: tuple[OptionContract, ...],
    quotes: tuple[OptionQuote, ...],
) -> OptionChainSnapshot:
    return OptionChainSnapshot(
        chain_id="chain-1",
        underlying="SPY",
        session_date=date(2026, 7, 10),
        as_of_utc=DECISION,
        contracts=contracts,
        quotes=quotes,
        source="test",
        ingested_at_utc=DECISION,
    )


def event_calendar(*events: MarketEvent) -> EventCalendarSnapshot:
    return EventCalendarSnapshot(
        snapshot_id="events-1",
        as_of_utc=DECISION,
        covered_from_utc=DECISION,
        covered_through_utc=EXPIRATION + timedelta(days=60),
        events=events,
        source="test",
    )


def account(*, option_buying_power: str = "10000") -> AccountSnapshot:
    return AccountSnapshot(
        account_id_hash="account-hash",
        adapter="paper",
        as_of_utc=DECISION,
        currency="USD",
        cash=Decimal("10000"),
        net_liquidation=Decimal("20000"),
        buying_power=Decimal("20000"),
        option_buying_power=Decimal(option_buying_power),
        margin_type=MarginType.CASH,
        option_level="level_2",
    )


def capabilities(**changes: object) -> BrokerCapabilities:
    values = {
        "adapter": "paper",
        "as_of_utc": DECISION,
        "published_at_utc": DECISION,
        "supported_margin_types": (MarginType.CASH,),
        "option_levels": ("level_2",),
        "supports_equity_options": True,
        "supports_multi_leg": True,
        "supports_early_exercise_requests": True,
        "source": "test",
    }
    values.update(changes)
    return BrokerCapabilities(**values)  # type: ignore[arg-type]


def activity(
    contract_id: str,
    *,
    volume: int | None = 100,
    open_interest: int | None = 1000,
    required_buying_power: str | None = "5000",
) -> ContractActivity:
    return ContractActivity(
        contract_id=contract_id,
        as_of_utc=DECISION,
        volume=volume,
        open_interest=open_interest,
        required_option_buying_power=(
            Decimal(required_buying_power) if required_buying_power is not None else None
        ),
    )


def complete_context(*activities: ContractActivity) -> CandidateEligibilityContext:
    return CandidateEligibilityContext(
        activity_by_contract={item.contract_id: item for item in activities},
        event_calendar=event_calendar(),
        account=account(),
        broker_capabilities=capabilities(),
    )


def strict_policy(**changes: object) -> CandidateEligibilityPolicy:
    values = {
        "maximum_absolute_spread": Decimal("0.25"),
        "maximum_relative_spread": Decimal("0.25"),
        "minimum_volume": 10,
        "minimum_open_interest": 100,
        "require_capital_estimate": True,
    }
    values.update(changes)
    return CandidateEligibilityPolicy(**values)  # type: ignore[arg-type]


def test_enumeration_is_sorted_filtered_and_reproducible() -> None:
    selected = (
        contract("p610", "610"),
        contract("c600", "600", option_type=OptionType.CALL),
        contract("p590", "590"),
        contract("p600", "600"),
    )
    snapshot = chain(selected, tuple(quote(item.contract_id) for item in reversed(selected)))
    context = complete_context(*(activity(item.contract_id) for item in selected))
    selection = CandidateSelection(
        option_types=(OptionType.PUT,),
        minimum_strike=Decimal("595"),
        maximum_strike=Decimal("610"),
    )

    first = screen_option_candidates(
        snapshot,
        decision_at_utc=DECISION,
        strategy_id="weekend-short-put",
        strategy_version="1.0.0",
        selection=selection,
        policy=strict_policy(),
        context=context,
    )
    second = screen_option_candidates(
        replace(snapshot, contracts=tuple(reversed(selected))),
        decision_at_utc=DECISION,
        strategy_id="weekend-short-put",
        strategy_version="1.0.0",
        selection=selection,
        policy=strict_policy(),
        context=context,
    )

    assert [item.contract.contract_id for item in first] == ["p600", "p610"]
    assert [item.candidate_key for item in first] == [item.candidate_key for item in second]
    assert all(item.eligible for item in first)
    assert ScreenedContract.from_json(first[0].to_json()) == first[0]


def test_quote_and_liquidity_gates_retain_ordered_reason_codes() -> None:
    item = contract("bad", "600")
    snapshot = chain(
        (item,),
        (
            quote(
                "bad",
                bid="1.20",
                ask="1.00",
                as_of_utc=DECISION - timedelta(minutes=10),
                flags=(QuoteQualityFlag.CROSSED, QuoteQualityFlag.MISSING_SIZE),
                bid_size=None,
            ),
        ),
    )
    context = complete_context(activity("bad", volume=1, open_interest=2))

    result = screen_option_candidates(
        snapshot,
        decision_at_utc=DECISION,
        strategy_id="short-put",
        strategy_version="1",
        policy=strict_policy(),
        context=context,
    )[0]

    assert not result.eligible
    assert result.rejection_reasons == (
        CandidateRejectionCode.QUOTE_STALE,
        CandidateRejectionCode.QUOTE_CROSSED,
        CandidateRejectionCode.QUOTE_MISSING_SIZE,
        CandidateRejectionCode.VOLUME_BELOW_MINIMUM,
        CandidateRejectionCode.OPEN_INTEREST_BELOW_MINIMUM,
    )
    assert [reason.value for reason in result.rejection_reasons] == [
        "quote_stale",
        "quote_crossed",
        "quote_missing_size",
        "volume_below_minimum",
        "open_interest_below_minimum",
    ]


def test_missing_required_supplemental_inputs_fail_closed() -> None:
    item = contract("p600", "600")
    result = screen_option_candidates(
        chain((item,), (quote("p600"),)),
        decision_at_utc=DECISION,
        strategy_id="short-put",
        strategy_version="1",
        policy=strict_policy(),
    )[0]

    assert result.rejection_reasons == (
        CandidateRejectionCode.ACTIVITY_MISSING,
        CandidateRejectionCode.EVENT_CALENDAR_MISSING,
        CandidateRejectionCode.ACCOUNT_MISSING,
        CandidateRejectionCode.BROKER_CAPABILITIES_MISSING,
    )


def test_event_account_and_broker_gates_are_point_in_time() -> None:
    item = contract("p600", "600")
    earnings = MarketEvent(
        event_id="earnings-1",
        event_type=MarketEventType.EARNINGS,
        announced_at_utc=DECISION - timedelta(days=1),
        effective_at_utc=DECISION + timedelta(days=1),
        symbol="SPY",
        source="test",
        ingested_at_utc=DECISION - timedelta(days=1),
    )
    context = CandidateEligibilityContext(
        activity_by_contract={"p600": activity("p600", required_buying_power="5000")},
        event_calendar=event_calendar(earnings),
        account=account(option_buying_power="1000"),
        broker_capabilities=capabilities(
            supported_margin_types=(MarginType.REG_T,),
            supports_multi_leg=False,
        ),
    )
    result = screen_option_candidates(
        chain((item,), (quote("p600"),)),
        decision_at_utc=DECISION,
        strategy_id="spread",
        strategy_version="2",
        policy=strict_policy(blocked_event_types=(MarketEventType.EARNINGS,), required_leg_count=2),
        context=context,
    )[0]

    assert result.rejection_reasons == (
        CandidateRejectionCode.BLOCKED_EVENT,
        CandidateRejectionCode.ACCOUNT_OPTION_LEVEL_UNSUPPORTED,
        CandidateRejectionCode.MULTI_LEG_UNSUPPORTED,
        CandidateRejectionCode.INSUFFICIENT_OPTION_BUYING_POWER,
    )


def test_expired_contract_and_missing_quote_are_preserved() -> None:
    expired = contract("expired", "500", expiration_at_utc=DECISION - timedelta(minutes=1))
    result = screen_option_candidates(
        chain((expired,), ()),
        decision_at_utc=DECISION,
        strategy_id="audit",
        strategy_version="1",
        policy=CandidateEligibilityPolicy(
            require_event_calendar=False,
            require_account_and_capabilities=False,
        ),
    )[0]

    assert result.rejection_reasons == (
        CandidateRejectionCode.CONTRACT_EXPIRED,
        CandidateRejectionCode.QUOTE_MISSING,
    )


@pytest.mark.parametrize(
    "selection",
    [
        CandidateSelection(option_types=(OptionType.PUT,)),
        CandidateSelection(
            earliest_expiration_at_utc=EXPIRATION,
            latest_expiration_at_utc=EXPIRATION,
        ),
    ],
)
def test_selection_boundaries_are_inclusive(selection: CandidateSelection) -> None:
    item = contract("p600", "600")
    result = screen_option_candidates(
        chain((item,), (quote("p600"),)),
        decision_at_utc=DECISION,
        strategy_id="selection",
        strategy_version="1",
        selection=selection,
        policy=CandidateEligibilityPolicy(
            require_event_calendar=False,
            require_account_and_capabilities=False,
        ),
    )
    assert len(result) == 1
