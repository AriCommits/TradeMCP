"""Point-in-time event calendars with explicit knowledge and coverage times."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from .contracts import VersionedRecord, require_utc
from .market_inputs import MissingMarketInputError, StaleMarketInputError


class MarketEventType(str, Enum):
    EARNINGS = "earnings"
    ECONOMIC_RELEASE = "economic_release"
    CENTRAL_BANK = "central_bank"
    CONFERENCE = "conference"
    REGULATORY = "regulatory"
    OTHER = "other"


@dataclass(frozen=True)
class MarketEvent(VersionedRecord):
    event_id: str
    event_type: MarketEventType
    announced_at_utc: datetime
    effective_at_utc: datetime
    source: str
    ingested_at_utc: datetime
    symbol: str | None = None
    expected_value: Decimal | None = None
    actual_value: Decimal | None = None
    confidence: Decimal | None = None
    source_record_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("announced_at_utc", "effective_at_utc", "ingested_at_utc"):
            require_utc(getattr(self, name), name)
        if not self.event_id or not self.source:
            raise ValueError("event_id and source are required")
        if self.confidence is not None and not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence must be between zero and one")


@dataclass(frozen=True)
class EventCalendarSnapshot(VersionedRecord):
    snapshot_id: str
    as_of_utc: datetime
    covered_from_utc: datetime
    covered_through_utc: datetime
    events: tuple[MarketEvent, ...]
    source: str

    def __post_init__(self) -> None:
        for name in ("as_of_utc", "covered_from_utc", "covered_through_utc"):
            require_utc(getattr(self, name), name)
        if not self.snapshot_id or not self.source:
            raise ValueError("snapshot_id and source are required")
        if self.covered_through_utc < self.covered_from_utc:
            raise ValueError("event coverage interval is inverted")
        if any(event.announced_at_utc > self.as_of_utc for event in self.events):
            raise ValueError("snapshot cannot contain events announced after its as_of_utc")
        if any(event.ingested_at_utc > self.as_of_utc for event in self.events):
            raise ValueError("snapshot cannot contain events ingested after its as_of_utc")

    def events_between(
        self,
        start_at_utc: datetime,
        end_at_utc: datetime,
        symbol: str | None = None,
    ) -> tuple[MarketEvent, ...]:
        require_utc(start_at_utc, "start_at_utc")
        require_utc(end_at_utc, "end_at_utc")
        if start_at_utc < self.covered_from_utc or end_at_utc > self.covered_through_utc:
            raise MissingMarketInputError("event calendar does not cover requested interval")
        return tuple(
            event
            for event in self.events
            if start_at_utc <= event.effective_at_utc <= end_at_utc
            and (symbol is None or event.symbol in (None, symbol))
        )


class SavedEventProvider:
    def __init__(self, snapshots: tuple[EventCalendarSnapshot, ...]) -> None:
        self._snapshots = snapshots

    def snapshot(self, decision_at_utc: datetime, max_age: timedelta) -> EventCalendarSnapshot:
        require_utc(decision_at_utc, "decision_at_utc")
        eligible = tuple(
            snapshot for snapshot in self._snapshots if snapshot.as_of_utc <= decision_at_utc
        )
        if not eligible:
            raise MissingMarketInputError("no event calendar known at decision time")
        selected = max(eligible, key=lambda snapshot: snapshot.as_of_utc)
        if decision_at_utc - selected.as_of_utc > max_age:
            raise StaleMarketInputError("event calendar is stale")
        return selected
