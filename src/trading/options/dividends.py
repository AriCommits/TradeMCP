"""Point-in-time discrete dividends and corporate actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import cast

from .contracts import VersionedRecord, require_utc
from .market_inputs import MissingMarketInputError, StaleMarketInputError


class CorporateActionType(str, Enum):
    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    MERGER = "merger"
    SPINOFF = "spinoff"
    SYMBOL_CHANGE = "symbol_change"
    SPECIAL_DIVIDEND = "special_dividend"


@dataclass(frozen=True)
class DiscreteDividend(VersionedRecord):
    dividend_id: str
    symbol: str
    amount: Decimal
    currency: str
    ex_date: date
    payment_date: date | None
    announced_at_utc: datetime
    effective_at_utc: datetime
    source: str
    ingested_at_utc: datetime

    def __post_init__(self) -> None:
        for name in ("announced_at_utc", "effective_at_utc", "ingested_at_utc"):
            require_utc(getattr(self, name), name)
        if not self.dividend_id or not self.symbol or not self.source or self.amount < 0:
            raise ValueError("dividend identity/source are required and amount cannot be negative")
        if len(self.currency) != 3 or self.currency.upper() != self.currency:
            raise ValueError("currency must be an uppercase ISO-style code")


@dataclass(frozen=True)
class CorporateAction(VersionedRecord):
    action_id: str
    symbol: str
    action_type: CorporateActionType
    announced_at_utc: datetime
    effective_at_utc: datetime
    source: str
    ingested_at_utc: datetime
    ratio: Decimal | None = None
    cash_amount: Decimal | None = None
    new_symbol: str | None = None

    def __post_init__(self) -> None:
        for name in ("announced_at_utc", "effective_at_utc", "ingested_at_utc"):
            require_utc(getattr(self, name), name)
        if not self.action_id or not self.symbol or not self.source:
            raise ValueError("corporate action identity, symbol, and source are required")
        if self.ratio is not None and self.ratio <= 0:
            raise ValueError("corporate action ratio must be positive")
        if self.cash_amount is not None and self.cash_amount < 0:
            raise ValueError("cash_amount cannot be negative")


CorporateCalendarItem = DiscreteDividend | CorporateAction


@dataclass(frozen=True)
class CorporateCalendarSnapshot(VersionedRecord):
    symbol: str
    as_of_utc: datetime
    covered_through_utc: datetime
    dividends: tuple[DiscreteDividend, ...]
    actions: tuple[CorporateAction, ...]
    source: str

    def __post_init__(self) -> None:
        require_utc(self.as_of_utc, "as_of_utc")
        require_utc(self.covered_through_utc, "covered_through_utc")
        if not self.symbol or not self.source or self.covered_through_utc < self.as_of_utc:
            raise ValueError("valid symbol, source, and coverage interval are required")
        items = cast(
            tuple[CorporateCalendarItem, ...],
            (*self.dividends, *self.actions),
        )
        if any(item.symbol != self.symbol for item in items):
            raise ValueError("all corporate calendar items must match snapshot symbol")
        if any(item.announced_at_utc > self.as_of_utc for item in items):
            raise ValueError("snapshot cannot contain items not announced by as_of_utc")
        if any(item.ingested_at_utc > self.as_of_utc for item in items):
            raise ValueError("snapshot cannot contain items ingested after as_of_utc")

    def known_between(
        self, start_at_utc: datetime, end_at_utc: datetime
    ) -> tuple[CorporateCalendarItem, ...]:
        """Return known effective items, failing if the requested interval is not covered."""

        require_utc(start_at_utc, "start_at_utc")
        require_utc(end_at_utc, "end_at_utc")
        if start_at_utc < self.as_of_utc or end_at_utc > self.covered_through_utc:
            raise MissingMarketInputError("corporate calendar does not cover requested interval")
        items = cast(
            tuple[CorporateCalendarItem, ...],
            (*self.dividends, *self.actions),
        )
        return tuple(item for item in items if start_at_utc <= item.effective_at_utc <= end_at_utc)


class SavedCorporateCalendarProvider:
    def __init__(self, snapshots: tuple[CorporateCalendarSnapshot, ...]) -> None:
        self._snapshots = snapshots

    def snapshot(
        self, symbol: str, decision_at_utc: datetime, max_age: timedelta
    ) -> CorporateCalendarSnapshot:
        require_utc(decision_at_utc, "decision_at_utc")
        eligible = tuple(
            snapshot
            for snapshot in self._snapshots
            if snapshot.symbol == symbol and snapshot.as_of_utc <= decision_at_utc
        )
        if not eligible:
            raise MissingMarketInputError(f"no corporate calendar for {symbol}")
        selected = max(eligible, key=lambda snapshot: snapshot.as_of_utc)
        if decision_at_utc - selected.as_of_utc > max_age:
            raise StaleMarketInputError(f"corporate calendar for {symbol} is stale")
        return selected
