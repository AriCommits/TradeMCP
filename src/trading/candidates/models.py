"""Serializable inputs and outputs for deterministic option candidate screening."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from trading.accounts.records import BrokerCapabilities
from trading.options.contracts import OptionContract, OptionType, VersionedRecord, require_utc
from trading.options.events import EventCalendarSnapshot, MarketEventType
from trading.options.quotes import OptionQuote
from trading.strategies.specifications import AccountSnapshot


class CandidateRejectionCode(str, Enum):
    """Stable, machine-readable eligibility failures.

    Declaration order is the canonical display and serialization order.
    """

    SNAPSHOT_FROM_FUTURE = "snapshot_from_future"
    SNAPSHOT_STALE = "snapshot_stale"
    CONTRACT_EXPIRED = "contract_expired"
    QUOTE_MISSING = "quote_missing"
    QUOTE_FROM_FUTURE = "quote_from_future"
    QUOTE_STALE = "quote_stale"
    QUOTE_CROSSED = "quote_crossed"
    QUOTE_LOCKED = "quote_locked"
    QUOTE_ZERO_BID = "quote_zero_bid"
    QUOTE_MISSING_SIZE = "quote_missing_size"
    ABSOLUTE_SPREAD_EXCEEDED = "absolute_spread_exceeded"
    RELATIVE_SPREAD_EXCEEDED = "relative_spread_exceeded"
    ACTIVITY_MISSING = "activity_missing"
    VOLUME_BELOW_MINIMUM = "volume_below_minimum"
    OPEN_INTEREST_BELOW_MINIMUM = "open_interest_below_minimum"
    ACTIVITY_FROM_FUTURE = "activity_from_future"
    ACTIVITY_STALE = "activity_stale"
    EVENT_CALENDAR_MISSING = "event_calendar_missing"
    EVENT_CALENDAR_FROM_FUTURE = "event_calendar_from_future"
    EVENT_CALENDAR_STALE = "event_calendar_stale"
    EVENT_COVERAGE_MISSING = "event_coverage_missing"
    BLOCKED_EVENT = "blocked_event"
    ACCOUNT_MISSING = "account_missing"
    ACCOUNT_FROM_FUTURE = "account_from_future"
    ACCOUNT_STALE = "account_stale"
    BROKER_CAPABILITIES_MISSING = "broker_capabilities_missing"
    BROKER_CAPABILITIES_FROM_FUTURE = "broker_capabilities_from_future"
    BROKER_CAPABILITIES_STALE = "broker_capabilities_stale"
    BROKER_ADAPTER_MISMATCH = "broker_adapter_mismatch"
    EQUITY_OPTIONS_UNSUPPORTED = "equity_options_unsupported"
    ACCOUNT_OPTION_LEVEL_UNSUPPORTED = "account_option_level_unsupported"
    MULTI_LEG_UNSUPPORTED = "multi_leg_unsupported"
    CAPITAL_REQUIREMENT_MISSING = "capital_requirement_missing"
    INSUFFICIENT_OPTION_BUYING_POWER = "insufficient_option_buying_power"


@dataclass(frozen=True)
class ContractActivity(VersionedRecord):
    """Point-in-time volume, open interest, and optional capital estimate."""

    contract_id: str
    as_of_utc: datetime
    volume: int | None
    open_interest: int | None
    required_option_buying_power: Decimal | None = None

    def __post_init__(self) -> None:
        require_utc(self.as_of_utc, "as_of_utc")
        if not self.contract_id:
            raise ValueError("contract_id is required")
        if self.volume is not None and self.volume < 0:
            raise ValueError("volume cannot be negative")
        if self.open_interest is not None and self.open_interest < 0:
            raise ValueError("open_interest cannot be negative")
        if self.required_option_buying_power is not None and self.required_option_buying_power < 0:
            raise ValueError("required_option_buying_power cannot be negative")


@dataclass(frozen=True)
class CandidateSelection:
    """Defines the contract universe; eligibility policy is applied afterwards."""

    option_types: tuple[OptionType, ...] = (OptionType.CALL, OptionType.PUT)
    earliest_expiration_at_utc: datetime | None = None
    latest_expiration_at_utc: datetime | None = None
    minimum_strike: Decimal | None = None
    maximum_strike: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.option_types:
            raise ValueError("at least one option type is required")
        if len(set(self.option_types)) != len(self.option_types):
            raise ValueError("option_types must be unique")
        for name in ("earliest_expiration_at_utc", "latest_expiration_at_utc"):
            value = getattr(self, name)
            if value is not None:
                require_utc(value, name)
        if (
            self.earliest_expiration_at_utc is not None
            and self.latest_expiration_at_utc is not None
            and self.latest_expiration_at_utc < self.earliest_expiration_at_utc
        ):
            raise ValueError("expiration selection interval is inverted")
        if self.minimum_strike is not None and self.minimum_strike <= 0:
            raise ValueError("minimum_strike must be positive")
        if self.maximum_strike is not None and self.maximum_strike <= 0:
            raise ValueError("maximum_strike must be positive")
        if (
            self.minimum_strike is not None
            and self.maximum_strike is not None
            and self.maximum_strike < self.minimum_strike
        ):
            raise ValueError("strike selection interval is inverted")


@dataclass(frozen=True)
class CandidateEligibilityPolicy:
    max_snapshot_age: timedelta = timedelta(minutes=5)
    max_quote_age: timedelta = timedelta(minutes=5)
    max_activity_age: timedelta = timedelta(days=1)
    maximum_absolute_spread: Decimal | None = None
    maximum_relative_spread: Decimal | None = None
    minimum_volume: int = 0
    minimum_open_interest: int = 0
    reject_locked_quotes: bool = False
    reject_zero_bid: bool = True
    require_quote_sizes: bool = True
    require_event_calendar: bool = True
    max_event_calendar_age: timedelta = timedelta(days=1)
    blocked_event_types: tuple[MarketEventType, ...] = ()
    require_account_and_capabilities: bool = True
    max_account_age: timedelta = timedelta(days=1)
    max_capability_age: timedelta = timedelta(days=1)
    required_leg_count: int = 1
    require_capital_estimate: bool = False

    def __post_init__(self) -> None:
        durations = (
            self.max_snapshot_age,
            self.max_quote_age,
            self.max_activity_age,
            self.max_event_calendar_age,
            self.max_account_age,
            self.max_capability_age,
        )
        if any(value < timedelta(0) for value in durations):
            raise ValueError("freshness limits cannot be negative")
        if self.maximum_absolute_spread is not None and self.maximum_absolute_spread < 0:
            raise ValueError("maximum_absolute_spread cannot be negative")
        if self.maximum_relative_spread is not None and self.maximum_relative_spread < 0:
            raise ValueError("maximum_relative_spread cannot be negative")
        if self.minimum_volume < 0 or self.minimum_open_interest < 0:
            raise ValueError("liquidity minimums cannot be negative")
        if self.required_leg_count <= 0:
            raise ValueError("required_leg_count must be positive")
        if len(set(self.blocked_event_types)) != len(self.blocked_event_types):
            raise ValueError("blocked_event_types must be unique")


@dataclass(frozen=True)
class CandidateEligibilityContext:
    """Supplemental state that does not belong in a canonical quote snapshot."""

    activity_by_contract: Mapping[str, ContractActivity] = field(default_factory=dict)
    event_calendar: EventCalendarSnapshot | None = None
    account: AccountSnapshot | None = None
    broker_capabilities: BrokerCapabilities | None = None

    def __post_init__(self) -> None:
        activity = dict(self.activity_by_contract)
        if any(key != value.contract_id for key, value in activity.items()):
            raise ValueError("activity mapping keys must match contract_id values")
        object.__setattr__(self, "activity_by_contract", MappingProxyType(activity))


@dataclass(frozen=True)
class ScreenedContract(VersionedRecord):
    candidate_key: str
    chain_id: str
    strategy_id: str
    strategy_version: str
    decision_at_utc: datetime
    contract: OptionContract
    quote: OptionQuote | None
    activity: ContractActivity | None
    eligible: bool
    rejection_reasons: tuple[CandidateRejectionCode, ...]

    def __post_init__(self) -> None:
        require_utc(self.decision_at_utc, "decision_at_utc")
        if not self.candidate_key or not self.chain_id or not self.strategy_id:
            raise ValueError("candidate, chain, and strategy identifiers are required")
        if not self.strategy_version:
            raise ValueError("strategy_version is required")
        if self.quote is not None and self.quote.contract_id != self.contract.contract_id:
            raise ValueError("quote and contract identifiers do not match")
        if self.activity is not None and self.activity.contract_id != self.contract.contract_id:
            raise ValueError("activity and contract identifiers do not match")
        if self.eligible == bool(self.rejection_reasons):
            raise ValueError("eligible state and rejection reasons are inconsistent")
