"""Exchange sessions and exact option-expiration timestamps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .contracts import VersionedRecord, require_utc
from .market_inputs import MissingMarketInputError


@dataclass(frozen=True)
class ExchangeSession(VersionedRecord):
    exchange: str
    session_date: date
    opens_at_utc: datetime
    closes_at_utc: datetime
    source: str
    published_at_utc: datetime
    option_expiration_at_utc: datetime | None = None
    early_close: bool = False

    def __post_init__(self) -> None:
        for name in ("opens_at_utc", "closes_at_utc", "published_at_utc"):
            require_utc(getattr(self, name), name)
        if self.option_expiration_at_utc is not None:
            require_utc(self.option_expiration_at_utc, "option_expiration_at_utc")
        if not self.exchange or not self.source:
            raise ValueError("exchange and source are required")
        if self.closes_at_utc <= self.opens_at_utc:
            raise ValueError("session close must be after session open")


class SavedExchangeCalendar:
    """Exact saved sessions; never infers a missing holiday or expiration time."""

    def __init__(self, sessions: tuple[ExchangeSession, ...]) -> None:
        keys = {
            (session.exchange, session.session_date, session.published_at_utc)
            for session in sessions
        }
        if len(keys) != len(sessions):
            raise ValueError("exchange/session/publication rows must be unique")
        self._sessions = sessions

    def session(
        self, exchange: str, session_date: date, decision_at_utc: datetime
    ) -> ExchangeSession:
        require_utc(decision_at_utc, "decision_at_utc")
        eligible = tuple(
            row
            for row in self._sessions
            if row.exchange == exchange
            and row.session_date == session_date
            and row.published_at_utc <= decision_at_utc
        )
        if not eligible:
            raise MissingMarketInputError(
                f"no exchange session for {exchange} {session_date.isoformat()} known at decision"
            )
        return max(eligible, key=lambda row: row.published_at_utc)

    def expiration_at(
        self, exchange: str, session_date: date, decision_at_utc: datetime
    ) -> datetime:
        session = self.session(exchange, session_date, decision_at_utc)
        if session.option_expiration_at_utc is None:
            raise MissingMarketInputError(
                f"option expiration timestamp missing for {exchange} {session_date.isoformat()}"
            )
        return session.option_expiration_at_utc
