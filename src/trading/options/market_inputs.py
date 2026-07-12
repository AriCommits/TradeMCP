"""Shared point-in-time semantics for non-quote option market inputs."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol, TypeVar

from .contracts import require_utc


class MarketInputError(RuntimeError):
    """Base error for an input that cannot safely be used at a decision time."""


class MissingMarketInputError(MarketInputError):
    """Raised when no point-in-time input exists for the requested decision."""


class StaleMarketInputError(MarketInputError):
    """Raised when the newest eligible input is older than the accepted age."""


class PointInTimeRecord(Protocol):
    @property
    def as_of_utc(self) -> datetime: ...

    @property
    def published_at_utc(self) -> datetime: ...

    @property
    def ingested_at_utc(self) -> datetime: ...


RecordT = TypeVar("RecordT", bound=PointInTimeRecord)


def select_point_in_time(
    records: tuple[RecordT, ...],
    decision_at_utc: datetime,
    max_age: timedelta,
    description: str,
) -> RecordT:
    """Return the newest record knowable at ``decision_at_utc`` or fail closed."""

    require_utc(decision_at_utc, "decision_at_utc")
    if max_age < timedelta(0):
        raise ValueError("max_age cannot be negative")
    eligible = tuple(
        record
        for record in records
        if record.as_of_utc <= decision_at_utc
        and record.published_at_utc <= decision_at_utc
        and record.ingested_at_utc <= decision_at_utc
    )
    if not eligible:
        raise MissingMarketInputError(
            f"no point-in-time {description} available at {decision_at_utc.isoformat()}"
        )
    selected = max(eligible, key=lambda record: (record.as_of_utc, record.published_at_utc))
    age = decision_at_utc - selected.as_of_utc
    if age > max_age:
        raise StaleMarketInputError(
            f"{description} is stale by {age}; maximum accepted age is {max_age}"
        )
    return selected
