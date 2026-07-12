"""Point-in-time interest-rate and borrow/carry inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol

from .contracts import VersionedRecord, require_utc
from .market_inputs import select_point_in_time


@dataclass(frozen=True)
class RiskFreeRate(VersionedRecord):
    currency: str
    tenor_days: int
    annualized_rate: Decimal
    as_of_utc: datetime
    published_at_utc: datetime
    source: str
    ingested_at_utc: datetime
    source_record_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("as_of_utc", "published_at_utc", "ingested_at_utc"):
            require_utc(getattr(self, name), name)
        if len(self.currency) != 3 or self.currency.upper() != self.currency:
            raise ValueError("currency must be an uppercase ISO-style code")
        if self.tenor_days <= 0 or not self.source:
            raise ValueError("tenor_days must be positive and source is required")
        if self.published_at_utc < self.as_of_utc:
            raise ValueError("published_at_utc cannot precede as_of_utc")


@dataclass(frozen=True)
class BorrowCarryRate(VersionedRecord):
    symbol: str
    annualized_borrow_rate: Decimal
    as_of_utc: datetime
    published_at_utc: datetime
    source: str
    ingested_at_utc: datetime
    currency: str = "USD"
    source_record_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("as_of_utc", "published_at_utc", "ingested_at_utc"):
            require_utc(getattr(self, name), name)
        if not self.symbol or not self.source:
            raise ValueError("symbol and source are required")
        if len(self.currency) != 3 or self.currency.upper() != self.currency:
            raise ValueError("currency must be an uppercase ISO-style code")
        if self.published_at_utc < self.as_of_utc:
            raise ValueError("published_at_utc cannot precede as_of_utc")


class RateProvider(Protocol):
    def risk_free_rate(
        self, currency: str, tenor_days: int, decision_at_utc: datetime, max_age: timedelta
    ) -> RiskFreeRate: ...

    def borrow_rate(
        self, symbol: str, decision_at_utc: datetime, max_age: timedelta
    ) -> BorrowCarryRate: ...


class SavedRateProvider:
    """Credential-free provider over immutable saved rate fixtures."""

    def __init__(
        self,
        risk_free_rates: tuple[RiskFreeRate, ...],
        borrow_rates: tuple[BorrowCarryRate, ...],
    ) -> None:
        self._risk_free_rates = risk_free_rates
        self._borrow_rates = borrow_rates

    def risk_free_rate(
        self, currency: str, tenor_days: int, decision_at_utc: datetime, max_age: timedelta
    ) -> RiskFreeRate:
        records = tuple(
            record
            for record in self._risk_free_rates
            if record.currency == currency and record.tenor_days == tenor_days
        )
        return select_point_in_time(
            records, decision_at_utc, max_age, f"{currency} {tenor_days}-day risk-free rate"
        )

    def borrow_rate(
        self, symbol: str, decision_at_utc: datetime, max_age: timedelta
    ) -> BorrowCarryRate:
        records = tuple(record for record in self._borrow_rates if record.symbol == symbol)
        return select_point_in_time(records, decision_at_utc, max_age, f"{symbol} borrow rate")
