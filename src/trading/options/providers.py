"""Replaceable interfaces for point-in-time option market inputs."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Protocol

from .calendars import ExchangeSession
from .dividends import CorporateCalendarSnapshot
from .events import EventCalendarSnapshot


class CorporateCalendarProvider(Protocol):
    def snapshot(
        self, symbol: str, decision_at_utc: datetime, max_age: timedelta
    ) -> CorporateCalendarSnapshot: ...


class ExchangeCalendarProvider(Protocol):
    def session(
        self, exchange: str, session_date: date, decision_at_utc: datetime
    ) -> ExchangeSession: ...

    def expiration_at(
        self, exchange: str, session_date: date, decision_at_utc: datetime
    ) -> datetime: ...


class EventProvider(Protocol):
    def snapshot(self, decision_at_utc: datetime, max_age: timedelta) -> EventCalendarSnapshot: ...
